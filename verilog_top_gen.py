#!/usr/bin/env python3
"""Auto-generate a Verilog top module from submodule RTL files + a connection table.

Usage:
    python3 verilog_top_gen.py --rtl <files or dirs...> --conn connections.csv \
        --top-name top --out top.v

Connection CSV format (see examples/connections.csv):
    type,col1,col2,col3,col4,col5
    INSTANCE,<instance_name>,<module_name>,,,
    NET,<net_name>,<instance_name or TOP>,<port_name>,<net bits (optional)>,<port bits (optional)>

- An INSTANCE row declares one submodule instance.
- A NET row declares one endpoint of a net: which instance/port it attaches to.
  All NET rows sharing the same net name are tied together.
  Use instance name "TOP" to expose that endpoint as a port of the generated
  top module (its direction/width are inferred from the submodule port(s)
  it connects to).

Ports on the same net do not need to be the same width. When they differ,
the net is declared at the widest connected port's width, and each endpoint
is connected as-is: Verilog automatically zero-extends a narrower connection
or truncates a wider one, aligned at the LSB (this is standard IEEE
1364/1800 port-connection behavior, e.g. an 8-bit output connecting to a
32-bit input pads the upper 24 bits with 0). To place a signal at specific
bits of the net instead of the LSB-aligned default (e.g. packing a byte
into the upper half of a word), set the optional 5th column ("bits", the
net's own bit range) on that NET row to an explicit part-select such as
"[23:16]" or "[3]".

To instead take an arbitrary slice out of a wide port itself (e.g. only
bits [23:16] of a 32-bit output bus) and place that slice anywhere on the
net, set the optional 6th column ("port_bits") to that port-side part-select.
Verilog can't slice a formal port name in an instance connection, so when
"port_bits" is given the generator connects the port to an internal helper
wire in full and adds an `assign` statement linking the requested slice of
that helper wire to the requested slice of the net (net-side slice from
"bits", defaulting to the LSBs when blank).

To tie part of a net to a fixed value instead of a real port (e.g. tie off
unused lanes of a packed bus, or a constant status bit), use the special
instance name "CONST" on a NET row: col3 holds a Verilog literal (such as
"4'hA" or "1'b1") instead of a port name, and col4 ("bits") is required so
the generator knows where on the net to place it - a plain
`assign net[bits] = <literal>;` is emitted, any width (including a single
bit) at any position. A real single-bit port needs no special handling at
all: it already places at an arbitrary position the same way any port
does, via the "bits" column.

Pass --report <path> to also write a CSV listing every instance port and
its status: UNCONNECTED (no NET row at all), PARTIALLY_DRIVEN (the port
reads a net that has bits nothing ever drives, e.g. only part of a wide
bus is fed by "bits"/"port_bits" endpoints elsewhere), or CONNECTED.
UNCONNECTED and PARTIALLY_DRIVEN ports are listed first, then a blank
line, then fully CONNECTED ports.
"""
import argparse
import csv
import glob
import os
import re
import sys
from dataclasses import dataclass

TOP_INSTANCE = "TOP"
CONST_INSTANCE = "CONST"
DIRECTIONS = ("input", "output", "inout")


@dataclass
class Port:
    name: str
    direction: str  # 'input' | 'output' | 'inout'
    width: str      # e.g. '[31:0]' or '' for 1-bit


def bit_count(width_str):
    """Number of bits implied by a port width string like '[31:0]', or None
    if it can't be evaluated numerically (e.g. a parameterized width)."""
    if not width_str:
        return 1
    m = re.match(r"^\[(\d+):(\d+)\]$", width_str.strip())
    if m:
        return abs(int(m.group(1)) - int(m.group(2))) + 1
    return None


def parse_bit_range(bits_spec):
    """Inclusive (lo, hi) bit indices implied by a connection-CSV bits spec
    like '[23:16]' or '[3]'. Returns None for a blank spec."""
    bits_spec = (bits_spec or "").strip()
    if not bits_spec:
        return None
    m = re.match(r"^\[(\d+):(\d+)\]$", bits_spec)
    if m:
        hi, lo = int(m.group(1)), int(m.group(2))
        return (min(hi, lo), max(hi, lo))
    m = re.match(r"^\[(\d+)\]$", bits_spec)
    if m:
        return (int(m.group(1)), int(m.group(1)))
    raise ValueError("Invalid bits spec %r (expected e.g. [23:16] or [3])" % bits_spec)


def bits_spec_width(bits_spec):
    """Number of bits implied by a connection-CSV bits spec, or None for a
    blank spec."""
    r = parse_bit_range(bits_spec)
    return (r[1] - r[0] + 1) if r else None


def format_bit_set(bits):
    """Compact '[hi:lo],[hi:lo],...' description of a set of bit indices."""
    bits = sorted(bits)
    runs = []
    start = prev = bits[0]
    for b in bits[1:]:
        if b == prev + 1:
            prev = b
            continue
        runs.append((start, prev))
        start = prev = b
    runs.append((start, prev))
    return ",".join("[%d]" % lo if lo == hi else "[%d:%d]" % (hi, lo)
                     for lo, hi in runs)


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def split_top_level_commas(s):
    parts = []
    depth = 0
    cur = []
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def find_matching_paren(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("Unbalanced parentheses starting at %d" % open_idx)


def parse_ansi_port_entry(entry):
    """Parse one entry of an ANSI-style port list, e.g.
    'input wire signed [7:0] data = 0' -> (dir, width, name), or
    None if the entry has no direction keyword (non-ANSI list-of-names)."""
    tokens = entry.split()
    if not tokens or tokens[0] not in DIRECTIONS:
        return None
    direction = tokens[0]
    rest = " ".join(tokens[1:])
    rest = rest.split("=")[0].strip()  # drop default value
    m = re.search(r"\[[^\]]+\]", rest)
    width = m.group(0) if m else ""
    rest_no_width = re.sub(r"\[[^\]]+\]", " ", rest)
    words = [w for w in rest_no_width.split()
             if w not in ("wire", "reg", "logic", "signed", "unsigned",
                          "tri", "tri0", "tri1", "supply0", "supply1")]
    if not words:
        raise ValueError("Could not find port name in entry: %r" % entry)
    name = words[-1]
    return direction, width, name


def parse_body_decls(body):
    """For non-ANSI modules: scan the module body for input/output/inout
    declarations and return {name: (direction, width)}."""
    decls = {}
    pattern = re.compile(
        r"\b(input|output|inout)\s+(reg|wire|logic|signed|unsigned|tri|tri0|tri1|supply0|supply1|\s)*"
        r"(\[[^\]]+\])?\s*([A-Za-z_][\w\s,]*);"
    )
    for m in pattern.finditer(body):
        direction = m.group(1)
        width = m.group(3) or ""
        names = split_top_level_commas(m.group(4))
        for n in names:
            n = n.strip().split("=")[0].strip()
            if n:
                decls[n] = (direction, width)
    return decls


def parse_verilog_modules(text):
    """Return {module_name: [Port, ...]} for every module found in text."""
    text = strip_comments(text)
    modules = {}
    for m in re.finditer(r"\bmodule\s+([A-Za-z_]\w*)", text):
        module_name = m.group(1)
        pos = m.end()
        # skip optional #( ... ) parameter list
        skip = re.match(r"\s*#\s*\(", text[pos:])
        if skip:
            open_idx = pos + skip.end() - 1
            close_idx = find_matching_paren(text, open_idx)
            pos = close_idx + 1
        open_paren = text.find("(", pos)
        semi_before = text.find(";", pos)
        if open_paren == -1 or (semi_before != -1 and semi_before < open_paren):
            # module with no port list at all
            port_list_text = ""
            after_ports = pos
        else:
            close_paren = find_matching_paren(text, open_paren)
            port_list_text = text[open_paren + 1:close_paren]
            after_ports = close_paren + 1
        end_mod = text.find("endmodule", after_ports)
        body = text[after_ports:end_mod if end_mod != -1 else len(text)]

        entries = split_top_level_commas(port_list_text)
        ports = []
        plain_names = []
        for entry in entries:
            parsed = parse_ansi_port_entry(entry)
            if parsed is None:
                # non-ANSI: bare identifier, look up direction/width in body
                bare_name = entry.split("=")[0].strip()
                if bare_name:
                    plain_names.append(bare_name)
            else:
                direction, width, port_name = parsed
                ports.append(Port(port_name, direction, width))

        if plain_names:
            decls = parse_body_decls(body)
            for n in plain_names:
                if n not in decls:
                    raise ValueError(
                        "Module %s: could not find input/output/inout "
                        "declaration for port %r" % (module_name, n))
                direction, width = decls[n]
                ports.append(Port(n, direction, width))

        modules[module_name] = ports
    return modules


def collect_source_files(rtl_paths, recursive):
    files = []
    for p in rtl_paths:
        if os.path.isdir(p):
            for ext in ("*.v", "*.sv"):
                globpat = os.path.join(p, "**", ext) if recursive else os.path.join(p, ext)
                files.extend(sorted(glob.glob(globpat, recursive=recursive)))
        else:
            files.append(p)
    # de-duplicate, preserve order
    seen = set()
    unique = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique


def load_module_library(rtl_paths, recursive):
    library = {}
    for path in collect_source_files(rtl_paths, recursive):
        with open(path, "r") as f:
            text = f.read()
        for name, ports in parse_verilog_modules(text).items():
            if name in library:
                print("Warning: module %r found in multiple files; using %s"
                      % (name, path), file=sys.stderr)
            library[name] = ports
    return library


def read_connections(conn_path):
    instances = {}   # instance_name -> module_name
    nets = {}         # net_name -> [(instance_or_TOP, port_name, net_bits, port_bits), ...]
    with open(conn_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rtype = (row.get("type") or "").strip().upper()
            if not rtype or rtype.startswith("#"):
                continue
            col1 = (row.get("col1") or "").strip()
            col2 = (row.get("col2") or "").strip()
            col3 = (row.get("col3") or "").strip()
            col4 = (row.get("col4") or "").strip()
            col5 = (row.get("col5") or "").strip()
            if rtype == "INSTANCE":
                instance_name, module_name = col1, col2
                if instance_name in instances:
                    raise ValueError("Duplicate instance name: %s" % instance_name)
                instances[instance_name] = module_name
            elif rtype == "NET":
                net_name, inst_name, port_name, net_bits, port_bits = col1, col2, col3, col4, col5
                nets.setdefault(net_name, []).append((inst_name, port_name, net_bits, port_bits))
            else:
                raise ValueError("Unknown row type: %r" % rtype)
    return instances, nets


def generate_top(top_name, instances, nets, library):
    top_ports = []       # list of Port for the generated module header
    wire_decls = []       # list of (width, wire_name)
    conn_signal = {}      # (instance_name, port_name) -> signal name to use

    def resolve_port(inst_name, port_name):
        module_name = instances.get(inst_name)
        if module_name is None:
            raise ValueError("NET references unknown instance %r" % inst_name)
        ports = library.get(module_name)
        if ports is None:
            raise ValueError("Module %r (instance %r) not found in RTL library"
                              % (module_name, inst_name))
        for p in ports:
            if p.name == port_name:
                return p
        raise ValueError("Module %r has no port %r (instance %r)"
                          % (module_name, port_name, inst_name))

    assign_stmts = []      # list of Verilog "assign ...;" statement strings
    shadow_declared = set()  # (instance, port) pairs already given a helper wire
    partial_driven = {}      # (instance, port) -> format_bit_set() of undriven bits it reads

    def endpoint_expr(signal_base, net_bits):
        return "%s%s" % (signal_base, net_bits) if net_bits else signal_base

    def endpoint_width(net_bits, port_bits, port):
        """Minimum net width (bit count, from net bit 0) this endpoint requires."""
        if net_bits:
            # net_bits addresses an absolute position on the net, so the net
            # must be at least as wide as the highest index referenced.
            return parse_bit_range(net_bits)[1] + 1
        if port_bits:
            # No net_bits given: this port-side slice defaults to the net's
            # LSBs, so it only needs its own span width.
            return bits_spec_width(port_bits)
        return bit_count(port.width)

    def endpoint_range(net_bits, port_bits, port):
        """Inclusive (lo, hi) bit range this endpoint occupies on the net."""
        r = parse_bit_range(net_bits)
        if r:
            return r
        w = endpoint_width(net_bits, port_bits, port)
        return (0, w - 1) if w is not None else None  # unknown: assume full width

    for net_name, endpoints in nets.items():
        const_endpoints = [(p, nb, pb) for i, p, nb, pb in endpoints if i == CONST_INSTANCE]
        internal = [(i, p, nb, pb) for i, p, nb, pb in endpoints
                    if i not in (TOP_INSTANCE, CONST_INSTANCE)]
        external = [(i, p, nb, pb) for i, p, nb, pb in endpoints if i == TOP_INSTANCE]

        for value, nb, pb in const_endpoints:
            if not nb:
                raise ValueError(
                    "CONST endpoint on net %r (value %r) requires an explicit "
                    "'bits' column specifying where to place it" % (net_name, value))
            if pb:
                raise ValueError(
                    "CONST endpoint on net %r (value %r): 'port_bits' isn't "
                    "meaningful for a constant; leave col5 blank" % (net_name, value))

        resolved_internal = [(i, p, nb, pb, resolve_port(i, p)) for i, p, nb, pb in internal]

        for i, p, nb, pb, port in resolved_internal:
            if not pb:
                continue
            port_bit_count = bit_count(port.width)
            pb_range = parse_bit_range(pb)
            if port_bit_count is not None and pb_range and pb_range[1] >= port_bit_count:
                raise ValueError(
                    "Endpoint %s.%s: port_bits %r exceeds the port's own width %s "
                    "(%d bits)" % (i, p, pb, port.width or "1 bit", port_bit_count))

        any_bits = any(nb or pb for _, _, nb, pb in internal) or bool(const_endpoints)
        distinct_widths = {port.width for _, _, _, _, port in resolved_internal}

        if not any_bits and len(distinct_widths) <= 1:
            width = next(iter(distinct_widths), "")
        else:
            required = [(i, p, nb, pb, port, endpoint_width(nb, pb, port))
                        for i, p, nb, pb, port in resolved_internal]
            numeric_bits = [r for *_, r in required if r is not None]
            numeric_bits += [parse_bit_range(nb)[1] + 1 for _, nb, _ in const_endpoints]
            if not numeric_bits:
                raise ValueError(
                    "Net %r mixes port widths that can't be auto-resolved (%s); "
                    "give each endpoint an explicit 'bits' or 'port_bits' column"
                    % (net_name, ", ".join(
                        "%s.%s=%s" % (i, p, port.width or "1 bit")
                        for i, p, _, _, port in resolved_internal)))
            max_bits = max(numeric_bits)
            width = "[%d:0]" % (max_bits - 1) if max_bits > 1 else ""
            auto_mismatched = [(i, p, port.width) for i, p, nb, pb, port, r in required
                                if not nb and not pb and r is not None and r != max_bits]
            if auto_mismatched:
                print("Warning: net %r auto-extends/truncates at the LSB for %s "
                      "(net declared as %s); add an explicit 'bits' column to "
                      "control placement instead"
                      % (net_name, ", ".join(
                          "%s.%s=%s" % (i, p, w or "1 bit") for i, p, w in auto_mismatched),
                         width or "1 bit"),
                      file=sys.stderr)

        drivers = [(i, p, nb, pb, port) for i, p, nb, pb, port in resolved_internal
                   if port.direction in ("output", "inout")]
        driver_labels = ["%s.%s" % (i, p) for i, p, _, _, _ in drivers]
        driver_labels += ["CONST(%s)" % value for value, _, _ in const_endpoints]
        driver_ranges = [endpoint_range(nb, pb, port) for _, _, nb, pb, port in drivers]
        driver_ranges += [parse_bit_range(nb) for _, nb, _ in const_endpoints]
        if len(driver_ranges) > 1:
            overlapping = False
            for a in range(len(driver_ranges)):
                for c in range(a + 1, len(driver_ranges)):
                    ra, rc = driver_ranges[a], driver_ranges[c]
                    if ra is None or rc is None or not (ra[1] < rc[0] or ra[0] > rc[1]):
                        overlapping = True
            if overlapping:
                print("Warning: net %r has multiple drivers that overlap (%s)"
                      % (net_name, ", ".join(driver_labels)), file=sys.stderr)

        net_width_bits = bit_count(width)
        externally_supplied = bool(external) and not drivers and not const_endpoints
        if net_width_bits and not externally_supplied:
            driven_bits = set()
            for _, _, nb, _, _ in drivers:
                # A bare (no net_bits) driver zero-extends to cover the whole
                # net (verified against iverilog); an explicit net_bits slice
                # drives only that range.
                r = parse_bit_range(nb) if nb else (0, net_width_bits - 1)
                driven_bits.update(range(r[0], r[1] + 1))
            for _, nb, _ in const_endpoints:
                r = parse_bit_range(nb)
                driven_bits.update(range(r[0], r[1] + 1))
            undriven_bits = set(range(net_width_bits)) - driven_bits
            if undriven_bits:
                for i, p, nb, pb, port in resolved_internal:
                    if port.direction == "output":
                        continue
                    r = endpoint_range(nb, pb, port)
                    if r is None:
                        continue
                    read_bits = set(range(r[0], r[1] + 1))
                    gap = read_bits & undriven_bits
                    if gap:
                        driven_part = read_bits - gap
                        partial_driven[(i, p)] = (
                            format_bit_set(driven_part) if driven_part else "",
                            format_bit_set(gap),
                        )
                        module_name = instances.get(i, "?")
                        print("Warning: %s.%s (instance %s) reads net %r but bit(s) %s "
                              "of it are never driven"
                              % (module_name, p, i, net_name, format_bit_set(gap)),
                              file=sys.stderr)

        if external:
            if drivers:
                direction = drivers[0][4].direction
            elif const_endpoints:
                direction = "output"
            else:
                direction = "input"
            for _, port_name, _, _ in external:
                top_ports.append(Port(port_name, direction, width))
                # if multiple TOP endpoints share a net with a different
                # port name, alias them to the same net_name signal.
        elif internal or const_endpoints:
            # declare a wire even for a single dangling endpoint so the
            # instance can still connect to something.
            wire_decls.append((width, net_name))

        for value, nb, _ in const_endpoints:
            assign_stmts.append("assign %s = %s;" % (endpoint_expr(net_name, nb), value))

        for i, p, nb, pb, port in resolved_internal:
            if not pb:
                conn_signal[(i, p)] = endpoint_expr(net_name, nb)
                continue
            # Verilog can't slice a formal port name in an instance
            # connection, so route it through a full-width helper wire and
            # link the requested slices with a separate assign statement.
            shadow_name = "__slice_%s_%s" % (i, p)
            if (i, p) not in shadow_declared:
                port_bit_count = bit_count(port.width)
                shadow_width = "[%d:0]" % (port_bit_count - 1) if (port_bit_count or 0) > 1 else ""
                wire_decls.append((shadow_width, shadow_name))
                shadow_declared.add((i, p))
            conn_signal[(i, p)] = shadow_name
            net_target = endpoint_expr(net_name, nb)
            if port.direction in ("output", "inout"):
                assign_stmts.append("assign %s = %s%s;" % (net_target, shadow_name, pb))
            else:
                assign_stmts.append("assign %s%s = %s;" % (shadow_name, pb, net_target))

    lines = []
    lines.append("module %s (" % top_name)
    port_lines = []
    for port in top_ports:
        decl = "%s %s%s" % (
            port.direction, port.width + " " if port.width else "", port.name)
        decl = re.sub(r"\s+", " ", decl).strip()
        port_lines.append("    " + decl)
    lines.append(",\n".join(port_lines))
    lines.append(");")
    lines.append("")

    if wire_decls:
        for width, wname in wire_decls:
            decl = "wire %s%s;" % (width + " " if width else "", wname)
            lines.append("    " + re.sub(r"\s+", " ", decl))
        lines.append("")

    if assign_stmts:
        for stmt in assign_stmts:
            lines.append("    " + stmt)
        lines.append("")

    report = []
    for inst_name, module_name in instances.items():
        ports = library.get(module_name)
        if ports is None:
            raise ValueError("Module %r not found in RTL library" % module_name)
        lines.append("    %s %s (" % (module_name, inst_name))
        conn_lines = []
        for port in ports:
            sig = conn_signal.get((inst_name, port.name))
            connected = sig is not None
            driven_bits_desc = undriven_bits_desc = ""
            if not connected:
                print("Warning: %s.%s (instance %s) is unconnected"
                      % (module_name, port.name, inst_name), file=sys.stderr)
                sig = ""
                status = "UNCONNECTED"
            elif (inst_name, port.name) in partial_driven:
                status = "PARTIALLY_DRIVEN"
                driven_bits_desc, undriven_bits_desc = partial_driven[(inst_name, port.name)]
            else:
                status = "CONNECTED"
            report.append({
                "instance": inst_name,
                "module": module_name,
                "port": port.name,
                "direction": port.direction,
                "width": port.width or "1",
                "status": status,
                "signal": sig,
                "driven_bits": driven_bits_desc,
                "undriven_bits": undriven_bits_desc,
            })
            conn_lines.append("        .%s(%s)" % (port.name, sig))
        lines.append(",\n".join(conn_lines))
        lines.append("    );")
        lines.append("")

    lines.append("endmodule")
    return "\n".join(lines) + "\n", report


def write_connection_report(report, path):
    """Write a CSV report of every instance port's connection status, in
    three blocks separated by a blank line: UNCONNECTED, PARTIALLY_DRIVEN
    (with the driven/undriven bit ranges it reads), then CONNECTED."""
    def row(r):
        return [r["instance"], r["module"], r["port"], r["direction"],
                r["width"], r["signal"], r["driven_bits"], r["undriven_bits"],
                r["status"]]

    unconnected = [r for r in report if r["status"] == "UNCONNECTED"]
    partially_driven = [r for r in report if r["status"] == "PARTIALLY_DRIVEN"]
    connected = [r for r in report if r["status"] == "CONNECTED"]

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instance", "module", "port", "direction", "width", "signal",
                          "driven_bits", "undriven_bits", "status"])
        for r in unconnected:
            writer.writerow(row(r))
        writer.writerow([])
        for r in partially_driven:
            writer.writerow(row(r))
        writer.writerow([])
        for r in connected:
            writer.writerow(row(r))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rtl", nargs="+", required=True,
                     help="Submodule .v/.sv files and/or directories")
    ap.add_argument("--conn", required=True, help="Connection info CSV file")
    ap.add_argument("--top-name", default="top", help="Name of the generated top module")
    ap.add_argument("--out", help="Output .v file (default: stdout)")
    ap.add_argument("--recursive", action="store_true",
                     help="Recurse into directories given via --rtl")
    ap.add_argument("--report",
                     help="Write a CSV connection report (instance,module,port,"
                          "direction,width,signal,status) listing every instance "
                          "port as CONNECTED or UNCONNECTED")
    args = ap.parse_args()

    library = load_module_library(args.rtl, args.recursive)
    instances, nets = read_connections(args.conn)
    verilog, report = generate_top(args.top_name, instances, nets, library)

    if args.out:
        with open(args.out, "w") as f:
            f.write(verilog)
        print("Wrote %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(verilog)

    if args.report:
        write_connection_report(report, args.report)
        unconnected = sum(1 for r in report if r["status"] == "UNCONNECTED")
        partially_driven = sum(1 for r in report if r["status"] == "PARTIALLY_DRIVEN")
        print("Wrote %s (%d/%d ports unconnected, %d partially driven)"
              % (args.report, unconnected, len(report), partially_driven), file=sys.stderr)


if __name__ == "__main__":
    main()
