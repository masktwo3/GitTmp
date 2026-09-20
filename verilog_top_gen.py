#!/usr/bin/env python3
"""Auto-generate a Verilog top module from submodule RTL files + a connection table.

Usage:
    python3 verilog_top_gen.py --rtl <files or dirs...> --conn connections.csv \
        --top-name top --out top.v

Connection CSV format (see examples/connections.csv):
    type,col1,col2,col3
    INSTANCE,<instance_name>,<module_name>,
    NET,<net_name>,<instance_name or TOP>,<port_name>

- An INSTANCE row declares one submodule instance.
- A NET row declares one endpoint of a net: which instance/port it attaches to.
  All NET rows sharing the same net name are tied together.
  Use instance name "TOP" to expose that endpoint as a port of the generated
  top module (its direction/width are inferred from the submodule port(s)
  it connects to).
"""
import argparse
import csv
import glob
import os
import re
import sys
from dataclasses import dataclass

TOP_INSTANCE = "TOP"
DIRECTIONS = ("input", "output", "inout")


@dataclass
class Port:
    name: str
    direction: str  # 'input' | 'output' | 'inout'
    width: str      # e.g. '[31:0]' or '' for 1-bit


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
    nets = {}         # net_name -> [(instance_or_TOP, port_name), ...]
    with open(conn_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rtype = (row.get("type") or "").strip().upper()
            if not rtype or rtype.startswith("#"):
                continue
            col1 = (row.get("col1") or "").strip()
            col2 = (row.get("col2") or "").strip()
            col3 = (row.get("col3") or "").strip()
            if rtype == "INSTANCE":
                instance_name, module_name = col1, col2
                if instance_name in instances:
                    raise ValueError("Duplicate instance name: %s" % instance_name)
                instances[instance_name] = module_name
            elif rtype == "NET":
                net_name, inst_name, port_name = col1, col2, col3
                nets.setdefault(net_name, []).append((inst_name, port_name))
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

    for net_name, endpoints in nets.items():
        internal = [(i, p) for i, p in endpoints if i != TOP_INSTANCE]
        external = [(i, p) for i, p in endpoints if i == TOP_INSTANCE]

        resolved_internal = [(i, p, resolve_port(i, p)) for i, p in internal]

        width = None
        for _, _, port in resolved_internal:
            if width is None:
                width = port.width
            elif width != port.width:
                raise ValueError(
                    "Width mismatch on net %r: %s vs %s"
                    % (net_name, width, port.width))
        if width is None:
            width = ""

        if external:
            drivers = [port for _, _, port in resolved_internal
                       if port.direction in ("output", "inout")]
            direction = drivers[0].direction if drivers else "input"
            signal_name = net_name
            for _, port_name in external:
                top_ports.append(Port(port_name, direction, width))
                # if multiple TOP endpoints share a net with a different
                # port name, alias them to the same net_name signal.
            for i, p in internal:
                conn_signal[(i, p)] = signal_name
        else:
            if len(internal) >= 2:
                drivers = [port for _, _, port in resolved_internal
                           if port.direction in ("output", "inout")]
                if len(drivers) > 1:
                    print("Warning: net %r has multiple driving ports (%s)"
                          % (net_name, ", ".join(d.name for d in drivers)),
                          file=sys.stderr)
                wire_decls.append((width, net_name))
            elif len(internal) == 1:
                # single dangling endpoint: still declare a wire so the
                # instance can connect to something.
                wire_decls.append((width, net_name))
            for i, p in internal:
                conn_signal[(i, p)] = net_name

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

    for inst_name, module_name in instances.items():
        ports = library.get(module_name)
        if ports is None:
            raise ValueError("Module %r not found in RTL library" % module_name)
        lines.append("    %s %s (" % (module_name, inst_name))
        conn_lines = []
        for port in ports:
            sig = conn_signal.get((inst_name, port.name))
            if sig is None:
                print("Warning: %s.%s (instance %s) is unconnected"
                      % (module_name, port.name, inst_name), file=sys.stderr)
                sig = ""
            conn_lines.append("        .%s(%s)" % (port.name, sig))
        lines.append(",\n".join(conn_lines))
        lines.append("    );")
        lines.append("")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


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
    args = ap.parse_args()

    library = load_module_library(args.rtl, args.recursive)
    instances, nets = read_connections(args.conn)
    verilog = generate_top(args.top_name, instances, nets, library)

    if args.out:
        with open(args.out, "w") as f:
            f.write(verilog)
        print("Wrote %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(verilog)


if __name__ == "__main__":
    main()
