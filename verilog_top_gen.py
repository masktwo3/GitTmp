#!/usr/bin/env python3
"""Auto-generate a Verilog top module from submodule RTL files + a connection table.

Usage:
    python3 verilog_top_gen.py --rtl <files or dirs...> --conn connections.csv \
        --top-name top --out top.v

Connection CSV format (see examples/connections.csv):
    type,col1,col2,col3,col4,col5,col6
    INSTANCE,<instance_name>,<module_name>,,,,
    NET,<in_instance or TOP>,<in_port>,<in_bits (optional)>,<out_instance, TOP, or CONST>,<out_port, or a literal for CONST>,<out_bits (optional)>

- An INSTANCE row declares one submodule instance.
- A NET row declares one point-to-point connection: the input (consuming)
  side is col1-col3, the output (driving) side is col4-col6. There is no
  net-name column. Instead, every real instance port - on either side of
  any row - gets its own dedicated wire named "w_<instance>_<port>"
  (declared once, the first time that port is referenced), and each row
  emits one `assign` statement linking the input side's wire (or slice of
  it) to the output side's wire/literal/TOP-port (or slice of it). Fan-out
  (one driver feeding several inputs) and fan-in/bus-packing (several
  different drivers each feeding a different bit range of one input port)
  both just fall out of repeating a row with one side unchanged - the
  shared port's wire is simply referenced by more than one assign. Use
  instance name "TOP" on the input side to expose that connection as an
  output port of the generated top module, or on the output side to expose
  it as an input port (both directions are determined directly by which
  side "TOP" appears on, not inferred).

Ports on either side do not need to be the same width. When they differ,
the input side's own wire (sized to its own declared RTL width) and the
output side's own wire are joined via a bare `assign`, and Verilog
automatically zero-extends a narrower connection or truncates a wider one,
aligned at the LSB (standard IEEE 1364/1800 assignment behavior). To place
a connection at a specific position of the input port's wire instead of
the LSB-aligned default, set col3 ("in_bits") to an explicit part-select
such as "[23:16]" or "[3]" - this is what every row sharing an input side
must set (to distinct, non-overlapping ranges) for bus packing to land
each contribution correctly.

To instead take an arbitrary slice out of a wide *output* port itself
(e.g. only bits [23:16] of a 32-bit output bus), set col6 ("out_bits") to
that output-side part-select - since every real port already has its own
full-width wire, this is just `assign <input target> = w_<out_inst>_<out_port>[out_bits];`.

To tie a connection to a fixed value instead of a real output port (e.g.
tie off unused lanes of a packed bus, or a constant status bit), use the
special instance name "CONST" on the output side: col5 holds a Verilog
literal (such as "4'hA" or "1'b1") instead of a port name. col3
("in_bits") is then required, since a constant has nowhere else to read
its placement from. A real single-bit port needs no special handling at
all: it already places at an arbitrary position the same way any port
does, via the normal "in_bits" column.

If either side of a NET row names a port declared "inout" in the RTL, the
row is treated as a bidirectional tie rather than a one-way connection:
`assign` can't model that (a continuous driver only pushes one direction),
so instead every endpoint that needs to share one physical net - both
sides of one row, and transitively every row that reuses one of those
endpoints - is connected directly to a single shared wire (or straight to
the TOP port, if one is in the group), with no assign and no separate
per-port wire. This means both real ports on either side of an inout row
must themselves be declared "inout" (an inout can't be tied to a plain
input/output port), CONST can't drive one, and col6 ("out_bits") isn't
supported (only whole-port structural connections are); col3 ("in_bits")
may still be used on the input side to place a narrower inout port at a
specific position within a wider shared net.

Pass --report <path> to also write a CSV listing every instance port and
its status: UNCONNECTED (no NET row at all), PARTIALLY_DRIVEN (the port
reads a net that has bits nothing ever drives, e.g. only part of a wide
bus is fed by "in_bits"/"out_bits" endpoints elsewhere), or CONNECTED.
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
    """Read INSTANCE rows and raw point-to-point NET rows from the
    connection CSV. Returns (instances, net_rows) where net_rows is a list
    of (in_inst, in_port, in_bits, out_inst, out_port, out_bits) tuples -
    one row per NET line, passed directly to generate_top()."""
    instances = {}   # instance_name -> module_name
    net_rows = []
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
            col6 = (row.get("col6") or "").strip()
            if rtype == "INSTANCE":
                instance_name, module_name = col1, col2
                if instance_name in instances:
                    raise ValueError("Duplicate instance name: %s" % instance_name)
                instances[instance_name] = module_name
            elif rtype == "NET":
                # NET,<in_inst or TOP>,<in_port>,<in_bits>,<out_inst, TOP, or CONST>,<out_port or literal>,<out_bits>
                in_inst, in_port, in_bits, out_inst, out_port, out_bits = (
                    col1, col2, col3, col4, col5, col6)
                if not in_inst or not in_port:
                    raise ValueError("NET row is missing its input instance/port: %r" % (row,))
                if not out_inst or not out_port:
                    raise ValueError("NET row is missing its output instance/port: %r" % (row,))
                if in_inst == CONST_INSTANCE:
                    raise ValueError(
                        "CONST can only be used on the output (driving) side of "
                        "a NET row, not the input side: %r" % (row,))
                net_rows.append((in_inst, in_port, in_bits, out_inst, out_port, out_bits))
            else:
                raise ValueError("Unknown row type: %r" % rtype)
    return instances, net_rows


class _InoutUnionFind:
    """Tiny union-find used only to group 'inout' endpoints that must share
    one physical wire (assign-based bridging can't preserve bidirectional
    flow, unlike input/output nets, so this narrow case needs real grouping)."""

    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def generate_top(top_name, instances, net_rows, library):
    top_ports = []       # list of Port for the generated module header
    wire_decls = []       # list of (width, wire_name)
    conn_signal = {}      # (instance_name, port_name) -> signal name to use
    assign_stmts = []      # list of Verilog "assign ...;" statement strings
    declared_ports = set()   # (instance, port) real ports already given a w_<inst>_<port> wire
    partial_driven = {}      # (instance, port) -> (driven_desc, undriven_desc)

    def resolve_port(inst_name, port_name):
        module_name = instances.get(inst_name)
        if module_name is None:
            raise ValueError("NET row references unknown instance %r" % inst_name)
        ports = library.get(module_name)
        if ports is None:
            raise ValueError("Module %r (instance %r) not found in RTL library"
                              % (module_name, inst_name))
        for p in ports:
            if p.name == port_name:
                return p
        raise ValueError("Module %r has no port %r (instance %r)"
                          % (module_name, port_name, inst_name))

    def endpoint_expr(signal_base, bits):
        return "%s%s" % (signal_base, bits) if bits else signal_base

    def ensure_port_wire(inst_name, port):
        """Declare (once) a dedicated wire w_<inst>_<port>, sized to that
        port's own width, and connect the instance's port to it bare."""
        key = (inst_name, port.name)
        wname = "w_%s_%s" % (inst_name, port.name)
        if key not in declared_ports:
            width_bits = bit_count(port.width)
            wstr = "[%d:0]" % (width_bits - 1) if (width_bits or 0) > 1 else ""
            wire_decls.append((wstr, wname))
            declared_ports.add(key)
            conn_signal[key] = wname
        return wname

    # --- pass 0: inout connections -- shared bidirectional wire, no assign ---
    # An 'inout' port can't be safely wired via assign (a continuous driver
    # only pushes one direction, breaking bidirectional flow), so instead we
    # group every endpoint that must share one physical net and connect all
    # of them directly to that single wire (or straight to the TOP port, if
    # one is in the group) -- no dedicated per-port wire, no assign.
    inout_rows, other_rows = [], []
    for row in net_rows:
        in_inst, in_port, in_bits, out_inst, out_port, out_bits = row
        in_is_inout = (in_inst != TOP_INSTANCE
                       and resolve_port(in_inst, in_port).direction == "inout")
        out_is_inout = (out_inst not in (TOP_INSTANCE, CONST_INSTANCE)
                         and resolve_port(out_inst, out_port).direction == "inout")
        if not (in_is_inout or out_is_inout):
            other_rows.append(row)
            continue
        if out_inst == CONST_INSTANCE:
            raise ValueError(
                "%s.%s is an 'inout' port; CONST cannot drive an inout "
                "connection" % (in_inst, in_port))
        if in_inst != TOP_INSTANCE and not in_is_inout:
            raise ValueError(
                "%s.%s is declared '%s' but this NET row ties it to an "
                "inout port; both real ports in an inout connection must "
                "be declared 'inout'"
                % (in_inst, in_port, resolve_port(in_inst, in_port).direction))
        if out_inst not in (TOP_INSTANCE, CONST_INSTANCE) and not out_is_inout:
            raise ValueError(
                "%s.%s is declared '%s' but this NET row ties it to an "
                "inout port; both real ports in an inout connection must "
                "be declared 'inout'"
                % (out_inst, out_port, resolve_port(out_inst, out_port).direction))
        if out_bits:
            raise ValueError(
                "NET row %r: output-side bits (col6) isn't supported for an "
                "inout connection (only whole-port structural connections "
                "are supported); place a narrower port within the shared "
                "net via the input-side 'bits' column instead" % (row,))
        inout_rows.append(row)
    net_rows = other_rows

    def inout_key(inst, port):
        return ("TOP", port) if inst == TOP_INSTANCE else ("PORT", inst, port)

    inout_uf = _InoutUnionFind()
    inout_position = {}   # endpoint_key -> (lo, hi) requested via in_bits
    for in_inst, in_port, in_bits, out_inst, out_port, out_bits in inout_rows:
        in_key = inout_key(in_inst, in_port)
        out_key = inout_key(out_inst, out_port)
        inout_uf.union(in_key, out_key)
        if in_bits and in_inst != TOP_INSTANCE:
            rng = parse_bit_range(in_bits)
            prev = inout_position.get(in_key)
            if prev is not None and prev != rng:
                raise ValueError(
                    "%s.%s: conflicting inout bit placements %s vs %s"
                    % (in_inst, in_port, rng, prev))
            inout_position[in_key] = rng

    inout_groups = {}
    for in_inst, in_port, _, out_inst, out_port, _ in inout_rows:
        for inst, port in ((in_inst, in_port), (out_inst, out_port)):
            key = inout_key(inst, port)
            inout_groups.setdefault(inout_uf.find(key), set()).add(key)

    for members in inout_groups.values():
        top_members = sorted(k[1] for k in members if k[0] == "TOP")
        if len(top_members) > 1:
            raise ValueError(
                "An inout net cannot be exposed as more than one TOP port "
                "(found: %s)" % ", ".join(top_members))
        port_members = sorted(k for k in members if k[0] == "PORT")

        widths = {k: (bit_count(resolve_port(k[1], k[2]).width) or 1) for k in port_members}
        canonical_width = max(
            [widths[k] for k in port_members]
            + [inout_position[k][1] + 1 for k in port_members if k in inout_position],
            default=1)
        width_str = "[%d:0]" % (canonical_width - 1) if canonical_width > 1 else ""

        if top_members:
            canonical_signal = top_members[0]
            top_ports.append(Port(canonical_signal, "inout", width_str))
        else:
            _, anchor_inst, anchor_port = port_members[0]
            canonical_signal = "w_%s_%s" % (anchor_inst, anchor_port)
            wire_decls.append((width_str, canonical_signal))

        for key in port_members:
            _, inst, port = key
            own_width = widths[key]
            if key in inout_position:
                lo, hi = inout_position[key]
                if hi - lo + 1 != own_width:
                    raise ValueError(
                        "%s.%s: inout bit placement %s must span exactly "
                        "its own width (%d bits)"
                        % (inst, port, format_bit_set(range(lo, hi + 1)), own_width))
                bits_str = "[%d]" % hi if hi == lo else "[%d:%d]" % (hi, lo)
                sig = "%s%s" % (canonical_signal, bits_str)
            elif own_width == canonical_width:
                sig = canonical_signal
            else:
                sig = "%s[%d:0]" % (canonical_signal, own_width - 1)
                print("Warning: %s.%s (inout, %d bits) auto-connects to the "
                      "low %d bits of the shared %d-bit inout net %s; add an "
                      "explicit input-side 'bits' column to control "
                      "placement instead"
                      % (inst, port, own_width, own_width, canonical_width, canonical_signal),
                      file=sys.stderr)
            conn_signal[(inst, port)] = sig
            declared_ports.add((inst, port))

    # --- pass 1: TOP ports fed by something inside (out_inst == TOP) ---
    top_as_producer = {}
    for in_inst, in_port, in_bits, out_inst, out_port, out_bits in net_rows:
        if out_inst == TOP_INSTANCE:
            top_as_producer.setdefault(out_port, []).append(
                (in_inst, in_port, in_bits, out_bits))

    for top_port_name, uses in top_as_producer.items():
        max_bits = 1
        for in_inst, in_port, in_bits, out_bits in uses:
            if out_bits:
                max_bits = max(max_bits, parse_bit_range(out_bits)[1] + 1)
            elif in_bits:
                max_bits = max(max_bits, parse_bit_range(in_bits)[1] + 1)
            elif in_inst != TOP_INSTANCE:
                max_bits = max(max_bits, bit_count(resolve_port(in_inst, in_port).width) or 1)
        width_str = "[%d:0]" % (max_bits - 1) if max_bits > 1 else ""
        top_ports.append(Port(top_port_name, "input", width_str))

    # --- pass 2: group rows by consumer (input-side) identity ---
    consumer_rows = {}
    for row in net_rows:
        in_inst, in_port = row[0], row[1]
        key = ("TOP", in_port) if in_inst == TOP_INSTANCE else ("PORT", in_inst, in_port)
        consumer_rows.setdefault(key, []).append(row)

    for key, rows in consumer_rows.items():
        is_top = key[0] == "TOP"
        if is_top:
            top_port_name = key[1]
            consumer_port = None
            own_width = None
        else:
            _, in_inst, in_port = key
            consumer_port = resolve_port(in_inst, in_port)
            if consumer_port.direction == "output":
                raise ValueError(
                    "%s.%s is declared 'output' in the RTL but is used on "
                    "the input side of a NET row" % (in_inst, in_port))
            own_width = bit_count(consumer_port.width)
            consumer_wire = ensure_port_wire(in_inst, consumer_port)

        resolved = []  # (row, (lo, hi), producer_expr, out_inst)
        for row in rows:
            in_inst, in_port, in_bits, out_inst, out_port, out_bits = row
            if out_inst == CONST_INSTANCE:
                if not in_bits:
                    raise ValueError(
                        "CONST endpoint (value %r) requires an explicit input-side "
                        "'bits' column specifying where to place it" % out_port)
                if out_bits:
                    raise ValueError(
                        "CONST endpoint (value %r): output-side bits isn't "
                        "meaningful for a constant; leave col6 blank" % out_port)
                producer_expr = out_port
                producer_default_width = None
            elif out_inst == TOP_INSTANCE:
                producer_expr = endpoint_expr(out_port, out_bits)
                producer_default_width = None
            else:
                producer_port = resolve_port(out_inst, out_port)
                if producer_port.direction == "input":
                    raise ValueError(
                        "%s.%s is declared 'input' in the RTL but is used on "
                        "the output side of a NET row" % (out_inst, out_port))
                if out_bits:
                    pbc = bit_count(producer_port.width)
                    pr = parse_bit_range(out_bits)
                    if pbc is not None and pr and pr[1] >= pbc:
                        raise ValueError(
                            "Endpoint %s.%s: output-side bits %r exceeds the port's "
                            "own width %s (%d bits)"
                            % (out_inst, out_port, out_bits, producer_port.width or "1 bit", pbc))
                producer_wire = ensure_port_wire(out_inst, producer_port)
                producer_expr = endpoint_expr(producer_wire, out_bits)
                producer_default_width = bit_count(producer_port.width)

            if in_bits:
                target_range = parse_bit_range(in_bits)
            elif own_width:
                target_range = (0, own_width - 1)
            elif producer_default_width:
                target_range = (0, producer_default_width - 1)
            else:
                target_range = (0, 0)

            if not is_top and own_width is not None and target_range[1] >= own_width:
                raise ValueError(
                    "%s.%s: input-side bits %r exceed the port's own width %s (%d bits)"
                    % (in_inst, in_port, in_bits, consumer_port.width or "1 bit", own_width))

            resolved.append((row, target_range, producer_expr, out_inst, producer_default_width))

        if is_top:
            max_bits = max(r[1][1] + 1 for r in resolved)
            width_str = "[%d:0]" % (max_bits - 1) if max_bits > 1 else ""
            top_ports.append(Port(top_port_name, "output", width_str))
            target_base = top_port_name
            final_width = max_bits
        else:
            target_base = consumer_wire
            final_width = own_width

        auto_mismatched = [
            (r[0][3], r[0][4], pdw) for r in resolved
            for pdw in [r[4]]
            if not r[0][2] and not r[0][5] and pdw is not None and pdw != final_width
        ]
        if auto_mismatched:
            target_label = top_port_name if is_top else "%s.%s" % (in_inst, in_port)
            print("Warning: %s auto-extends/truncates at the LSB for %s "
                  "(declared %d bits wide); add an explicit input-side 'bits' "
                  "column to control placement instead"
                  % (target_label, ", ".join(
                      "%s.%s=%d bits" % (oi, op, pdw) for oi, op, pdw in auto_mismatched),
                     final_width),
                  file=sys.stderr)

        ranges = [r[1] for r in resolved]
        if len(ranges) > 1:
            overlapping = any(
                not (ranges[a][1] < ranges[b][0] or ranges[b][1] < ranges[a][0])
                for a in range(len(ranges)) for b in range(a + 1, len(ranges)))
            if overlapping:
                labels = ["CONST(%s)" % r[0][4] if r[3] == CONST_INSTANCE
                          else "%s.%s" % (r[0][3], r[0][4]) for r in resolved]
                target_label = top_port_name if is_top else "%s.%s" % (in_inst, in_port)
                print("Warning: %s has multiple drivers that overlap (%s)"
                      % (target_label, ", ".join(labels)), file=sys.stderr)

        if not is_top and own_width:
            has_external = any(oi == TOP_INSTANCE for _, _, _, oi, _ in resolved)
            has_internal = any(oi != TOP_INSTANCE for _, _, _, oi, _ in resolved)
            externally_supplied = has_external and not has_internal
            if not externally_supplied:
                driven_bits = set()
                for _, (lo, hi), _, _, _ in resolved:
                    driven_bits.update(range(lo, hi + 1))
                undriven_bits = set(range(own_width)) - driven_bits
                if undriven_bits:
                    driven_part = driven_bits & set(range(own_width))
                    partial_driven[(in_inst, in_port)] = (
                        format_bit_set(driven_part) if driven_part else "",
                        format_bit_set(undriven_bits),
                    )
                    module_name = instances.get(in_inst, "?")
                    print("Warning: %s.%s (instance %s) reads w_%s_%s but bit(s) %s "
                          "of it are never driven"
                          % (module_name, in_port, in_inst, in_inst, in_port,
                             format_bit_set(undriven_bits)),
                          file=sys.stderr)

        for row, (lo, hi), producer_expr, out_inst, _ in resolved:
            in_bits_row = row[2]
            target_expr = endpoint_expr(target_base, in_bits_row)
            assign_stmts.append("assign %s = %s;" % (target_expr, producer_expr))

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
    instances, net_rows = read_connections(args.conn)
    verilog, report = generate_top(args.top_name, instances, net_rows, library)

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
