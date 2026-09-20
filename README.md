# gitest01

## verilog_top_gen.py

서브모듈 Verilog(.v/.sv) 파일들과 별도의 연결정보(connection) CSV 파일을 읽어
자동으로 top 모듈을 생성하는 스크립트입니다.

### 사용법

```bash
python3 verilog_top_gen.py \
    --rtl examples/cpu_core.v examples/memory.v \
    --conn examples/connections.csv \
    --top-name top \
    --out top.v \
    --report connection_report.csv
```

- `--rtl`: 서브모듈이 들어있는 `.v`/`.sv` 파일 또는 디렉터리 (여러 개 지정 가능).
  디렉터리를 지정하면 그 안의 `*.v`, `*.sv` 파일을 스캔합니다 (`--recursive`로 하위 폴더까지 스캔).
  각 파일의 포트 목록(ANSI 스타일/구식 스타일 모두 지원)을 자동으로 파싱합니다.
- `--conn`: 연결정보 CSV 파일.
- `--top-name`: 생성될 top 모듈 이름 (기본값 `top`).
- `--out`: 출력 파일 경로 (생략 시 표준출력).
- `--report`: (선택) top 모듈 생성 후, 모든 인스턴스의 모든 포트 상태를 CSV 파일로
  저장합니다. 컬럼:
  `instance,module,port,direction,width,signal,driven_bits,undriven_bits,status`
  (`status`가 마지막 컬럼). `status`는 세 가지 중 하나입니다:
  - `UNCONNECTED`: 그 포트를 가리키는 `NET` 행이 아예 없음.
  - `PARTIALLY_DRIVEN`: 포트는 어떤 net에 연결돼 있지만(`.port(net)`), 그 net(또는
    이 포트가 읽는 net의 구간) 중 실제로 아무도 구동(assign)하지 않는 비트가 있어서
    시뮬레이션에서 그 비트가 `z`로 뜨는 경우. 예를 들어 `bits`/`port_bits`로 버스의
    일부 레인만 채우고 나머지 레인은 채우지 않았는데, 그 net을 통째로 읽는 입력
    포트가 있을 때 발생합니다. 이때만 `driven_bits`(실제 구동되는 비트,
    예 `[27:8]`)와 `undriven_bits`(구동 안 되는 비트, 예 `[7:0],[31:28]`)에 값이
    채워지고, 그 외 상태에서는 두 컬럼 다 비어 있습니다.
  - `CONNECTED`: 포트가 연결돼 있고, 이 포트가 읽는 범위는 전부 구동됨.

  파일 안에서는 **`UNCONNECTED` 목록 → 빈 줄 → `PARTIALLY_DRIVEN` 목록 → 빈 줄 →
  `CONNECTED` 목록** 순서로 작성되어(각 구간이 비어 있어도 구분용 빈 줄은 항상
  들어갑니다), 문제 포트를 파일 맨 위에서 바로 확인할 수 있습니다.
  전부 연결된 예시는 `examples/connection_report.csv`, 일부러 몇 개를 빼서
  `UNCONNECTED`가 나오게 만든 예시는 `examples/unconnected_report/`,
  `PARTIALLY_DRIVEN`이 나오는 예시는 `examples/port_bits_packing/connection_report.csv`
  참고 (`wide_sink.packed_word`가 `driven_bits=[27:8]`,
  `undriven_bits=[7:0],[31:28]`, `status=PARTIALLY_DRIVEN`으로 표시됩니다).
  문제가 있는 포트가 있으면 콘솔에도 경고가 함께 출력됩니다.

### 연결정보 CSV 형식

`net_name`이라는 "허브" 개념이 없습니다. 대신 **한 행이 연결 하나(입력 쪽 ↔ 출력 쪽)를
직접 표현**합니다. `examples/connections.csv` 참고:

```csv
type,col1,col2,col3,col4,col5,col6
INSTANCE,u_cpu,cpu_core,,,,
INSTANCE,u_mem,memory,,,,
NET,u_cpu,clk,,TOP,clk,
NET,u_mem,clk,,TOP,clk,
NET,u_mem,addr_in,,u_cpu,addr_out,
```

- `INSTANCE` 행: `col1`=인스턴스 이름, `col2`=서브모듈 이름.
- `NET` 행: **입력(받는) 쪽이 `col1`~`col3`, 출력(주는) 쪽이 `col4`~`col6`**.
  - `col1`=입력 인스턴스 이름(또는 `TOP`), `col2`=입력 포트 이름, `col3`=입력 쪽 비트
    위치(선택).
  - `col4`=출력 인스턴스 이름(또는 `TOP`, `CONST`), `col5`=출력 포트 이름(`CONST`일 땐
    대신 Verilog 상수 literal), `col6`=출력 쪽 비트 위치(선택).
  - `col1`이 `TOP`이면 이 연결이 생성되는 top 모듈의 **출력 포트**로 노출되고,
    `col4`가 `TOP`이면 top 모듈의 **입력 포트**로 노출됩니다 (각 방향은 행 위치에서
    바로 결정되며 따로 추론하지 않습니다).
  - **net 이름을 따로 적지 않아도, 같은 입력 쪽 또는 같은 출력 쪽을 가진 행들은
    자동으로 하나의 wire로 묶입니다** (아래 참고). 내부 wire 이름은
    `w_<인스턴스>_<포트>`처럼 자동으로 생성됩니다 (사람이 읽는 용도일 뿐, 실제 동작에는
    영향 없음).

**같은 쪽을 반복해서 팬아웃/버스 패킹 표현하기**

- **팬아웃** (출력 하나가 여러 입력에 연결): 같은 출력 쪽(`col4`~`col6`)을 가진 행을
  여러 개 씁니다.
  ```csv
  NET,u_cpu,clk,,TOP,clk,
  NET,u_mem,clk,,TOP,clk,
  ```
  (`TOP`의 `clk` 입력 포트가 `u_cpu.clk`, `u_mem.clk` 양쪽을 동시에 구동)
- **버스 패킹/팬인** (서로 다른 여러 출력이 하나의 입력 포트를 비트 단위로 나눠 채움):
  같은 입력 쪽(`col1`~`col2`)을 가진 행을 여러 개 쓰고, 각 행의 `col3`(입력 쪽 비트
  위치)에 겹치지 않는 범위를 지정합니다.
  ```csv
  NET,u_sink,packed_word,[7:0],u_a,temp,
  NET,u_sink,packed_word,[15:8],u_b,pressure,
  ```

### 서브모듈 간 signal width가 다른 경우

연결되는 포트들의 비트 폭이 서로 다를 수 있습니다.

**1) 기본 동작 (자동 LSB 정렬)**

`col3`(입력 쪽 비트 위치)을 비워두면, 이 연결이 쓰는 wire는 필요한 만큼 가장 넓게
선언되고, 더 좁은 포트는 그대로(`.port(wire)`) 연결됩니다. Verilog 포트 연결 규칙(IEEE
1364/1800)에 따라 시뮬레이터/합성 툴이 자동으로 LSB 기준 zero-extend(입력 쪽) 또는
truncate를 수행합니다. 예: 8비트 `status` 출력을 32비트 `status_word` 입력에 연결하면
`status_word = {24'b0, status}`와 동일하게 동작합니다. 이 경우 스크립트가 경고를
출력하지만 에러로 중단하지는 않습니다.

```csv
NET,u_sink,status_word,,u_src,status,
```

**2) 명시적 비트 위치 지정 (`col3`)**

LSB가 아닌 특정 위치(예: 32비트 버스의 상위 바이트)에 신호를 놓고 싶다면 `col3`에
`[23:16]`, `[3]`처럼 명시적 part-select를 적어줍니다.

`examples/width_mismatch/`에 두 경우(자동 LSB 정렬 + 별개의 두 입력 포트가 각각 독립된
출력에 연결되는 경우) 모두를 iverilog로 검증한 예시가 있습니다.

**3) 버스 패킹: 여러 출력을 모아 하나의 넓은 입력 포트로 연결**

서로 다른 인스턴스의 여러 출력 포트가 같은 입력 포트를 겹치지 않는 위치에 나눠 채웁니다
(각 행의 `col1`~`col2`가 전부 같은 입력을 가리키고, `col3`만 다름):

```csv
INSTANCE,u_a,sensor_a,,,,
INSTANCE,u_b,sensor_b,,,,
INSTANCE,u_sink,packed_sink,,,,
NET,u_sink,packed_word,[7:0],u_a,temp,
NET,u_sink,packed_word,[15:8],u_b,pressure,
NET,u_sink,packed_word,[23:16],u_a,humidity,
NET,u_sink,packed_word,[31:24],u_b,battery,
```

`examples/bus_packing/`에서 서로 다른 두 모듈(`sensor_a`, `sensor_b`)의 8비트 출력 4개를
32비트 입력 포트의 각 바이트 레인에 배치해서 `packed_sink.packed_word`가
`packed_word=44332211`을 그대로 받는 것을 iverilog로 확인했습니다.

**4) 넓은 출력 포트의 임의 위치/임의 폭을 잘라서 연결 (`col6`, 출력 쪽 비트)**

출력 포트 자체가 넓은 버스이고, 그중 임의의 위치·임의의 폭만 잘라서 쓰고 싶다면
`col6`(출력 쪽 비트 위치)에 그 포트 자신의 part-select를 적어줍니다. `col3`(입력 쪽
비트 위치)은 그 조각을 연결의 어느 위치에 놓을지를 지정합니다 (비워두면 LSB).

```csv
NET,u_sink,packed_word,[15:8],u_a,data,[23:16]
NET,u_sink,packed_word,[27:16],u_b,data,[15:4]
```

위 예시는 `u_a.data`(32비트)의 `[23:16]` 8비트를 잘라서 `packed_word[15:8]`에, `u_b.data`
(32비트)의 `[15:4]` 12비트(바이트 경계가 아닌 임의 폭)를 잘라서 `packed_word[27:16]`에 각각
놓습니다.

Verilog는 인스턴스 연결에서 포트 이름 자체를 슬라이스할 수 없기 때문에(`.data[23:16](...)`
같은 문법은 불가), 출력 쪽 비트가 지정되면 스크립트가 자동으로 내부 helper wire를 만들어
포트 전체를 거기 연결한 뒤, `assign`문으로 helper wire의 지정된 구간과 연결의 지정된 구간을
이어줍니다:

```verilog
wire [31:0] __slice_u_a_data;
assign w_..._packed_word[15:8] = __slice_u_a_data[23:16];

wide_src_a u_a (
    .data(__slice_u_a_data)
);
```

`examples/port_bits_packing/`에서 서로 다른 두 모듈(`wide_src_a`=`0xAABBCCDD`,
`wide_src_b`=`0x11223344`)이 각각 위 위치의 값을 정확히 잘라내 연결의 지정된 위치에
심고, 나머지(구동되지 않은) 비트는 `z`로 뜨는 것까지 iverilog 시뮬레이션으로 확인했습니다
(`packed_word=z334bbzz`: `334`가 `[27:16]`, `bb`가 `[15:8]`).

**5) 상수 값 끼워 넣기 (`CONST`), 1비트 신호 배치**

입력 포트의 일부를 실제 출력 포트가 아니라 고정된 값으로 채우고 싶을 때(예: 버스의 남는
레인을 0으로 tie-off, 고정된 설정 값, 상수 status 비트)는 출력 쪽(`col4`)에 `CONST`를,
`col5`에 Verilog 리터럴을 적습니다. `col3`(입력 쪽 비트 위치)은 다른 행과 마찬가지로
위치를 지정하는 자리지만, `CONST`는 값을 어디에 둘지 알 방법이 없으므로 필수입니다.
`col6`(출력 쪽 비트)는 사용하지 않습니다. 폭은 리터럴 자체가 몇 비트인지(`4'hA`→4비트,
`1'b0`→1비트 등)와 무관하게 `col3`로 지정한 구간이 그대로 그 위치를 구동합니다:

```csv
NET,u_sink,packed_word,[31:28],CONST,4'hA,
NET,u_sink,packed_word,[6:0],CONST,7'h55,
```

한편 **1비트짜리 실제 신호**(포트 자체가 1비트인 경우)는 별도 기능 없이 기존 입력 쪽
비트 컬럼만으로 이미 임의 위치에 놓을 수 있습니다 (출력 쪽을 슬라이스할 필요가 없음 -
포트 자체가 이미 1비트이므로):

```csv
NET,u_sink,packed_word,[7],u_flag,flag,
```

`examples/const_and_bit_packing/`에서 4비트 상수(`4'hA` → `[31:28]`), 12비트/8비트
슬라이스(출력 쪽 비트로 잘라낸 `wide_src_a`/`wide_src_b`의 조각, `port_bits_packing`과
동일), 1비트 실제 신호(`flag_src.flag` → `[7]`), 7비트 상수(`7'h55` → `[6:0]`)를 모두 같은
입력(`u_sink.packed_word`)에 조합해 32비트를 빈틈없이 채우고, `PARTIALLY_DRIVEN` 없이
정확히 `packed_word=a334bbd5`로 조립되는 것을 iverilog로 확인했습니다. `CONST`에 입력 쪽
비트를 빼먹으면 명확한 에러로 중단되고, 다른 드라이버와 비트가 겹치면 "multiple drivers
that overlap" 경고가 뜨는 것까지 검증했습니다.

### 제한 사항

- 입력 쪽(`col1`/`col2`)에는 `CONST`를 쓸 수 없습니다(상수를 다른 상수가 읽을 수는
  없으므로) — 쓰면 에러로 중단됩니다.
- 행의 입력 쪽 포트가 RTL상 `output`으로 선언돼 있거나, 출력 쪽 포트가 `input`으로
  선언돼 있으면(방향이 행의 위치와 모순되면) 에러로 중단됩니다 (`inout`은 양쪽 다 허용).
- 입력 쪽 비트 범위와 포트 자체의 폭이 다르면(예: 8비트 포트에 `[15:0]` 지정), 그 부분은
  다시 Verilog의 자동 zero-extend/truncate 규칙을 따릅니다.
- 출력 쪽 비트가 그 포트의 실제 폭을 벗어나면(예: 8비트 포트에 `[15:8]` 지정) 에러로
  중단됩니다.
- 출력 쪽 비트로 연결이 실제로 구동되지 않는 비트가 생기면(위 `port_bits_packing`
  예시처럼 일부 구간만 채우는 경우) 그 비트는 시뮬레이션에서 `z`로 뜹니다. 전체 비트를
  채우려면 겹치지 않는 입력 쪽 비트로 모든 구간을 명시적으로 지정해야 합니다.
- 파라미터화된 폭(예: `[WIDTH-1:0]`)은 숫자로 환산할 수 없으므로, 그런 포트끼리 폭이 다르면
  각 행에 명시적으로 입력/출력 쪽 비트를 지정해야 하며, 지정하지 않으면 에러로 중단됩니다.
- `CONST` 행은 입력 쪽 비트(`col3`)가 필수이며, 빠지면 에러로 중단됩니다. 출력 쪽 비트
  (`col6`)는 아예 지원하지 않으며 값이 있으면 에러로 중단됩니다.
- 예전 형식(net 이름으로 묶던 방식)에서 가능했던 "출력 포트를 아무도 읽지 않는 wire에만
  연결"(dangling 단일 endpoint)은 이 형식에서는 표현할 수 없습니다 — 모든 행이 입력/출력
  양쪽을 다 가져야 하므로, 어딘가에 연결하지 않고 싶은 포트는 그냥 행을 적지 않으면
  `UNCONNECTED`로 잡힙니다.
- 포트가 연결정보에 없으면 경고를 출력하고 빈 연결(`.port()`)로 남겨둡니다.

`examples/` 디렉터리에 동작 예시(`cpu_core.v`, `memory.v`, `connections.csv`,
`width_mismatch/`, `bus_packing/`, `unconnected_report/`, `port_bits_packing/`,
`const_and_bit_packing/`)가 포함되어 있습니다.
