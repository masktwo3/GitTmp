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
- `--report`: (선택) top 모듈 생성 후, 모든 인스턴스의 모든 포트가 연결됐는지(`CONNECTED`)
  안 됐는지(`UNCONNECTED`)를 확인해 CSV 파일로 저장합니다. 컬럼:
  `instance,module,port,direction,width,signal,status` (`status`가 마지막 컬럼).
  파일 안에서는 헤더 다음 **미연결(UNCONNECTED) 포트 목록 → 빈 줄 → 연결(CONNECTED)
  포트 목록** 순서로 작성되어, 미연결 포트를 파일 맨 위에서 바로 확인할 수 있습니다.
  전부 연결된 예시는 `examples/connection_report.csv`, 일부러 몇 개를 빼서
  `UNCONNECTED`가 나오게 만든 예시는 `examples/unconnected_report/` 참고.
  연결이 안 된 포트가 있으면 콘솔에도 경고가 함께 출력됩니다.

### 연결정보 CSV 형식

`examples/connections.csv` 참고:

```csv
type,col1,col2,col3,col4
INSTANCE,u_cpu,cpu_core,,
INSTANCE,u_mem,memory,,
NET,clk,TOP,clk,
NET,clk,u_cpu,clk,
NET,clk,u_mem,clk,
NET,addr,u_cpu,addr_out,
NET,addr,u_mem,addr_in,
```

- `INSTANCE` 행: `col1`=인스턴스 이름, `col2`=서브모듈 이름.
- `NET` 행: `col1`=net(신호) 이름, `col2`=인스턴스 이름(또는 `TOP`), `col3`=포트 이름,
  `col4`=비트 위치 지정(선택, 아래 "서브모듈 간 signal width가 다른 경우" 참고).
  같은 net 이름을 가진 행들은 서로 연결된 것으로 취급됩니다.
  `col2`가 `TOP`이면 그 net은 생성되는 top 모듈의 외부 포트로 노출되며,
  방향(input/output/inout)과 비트 폭은 연결된 서브모듈 포트에서 자동으로 추론됩니다.

### 서브모듈 간 signal width가 다른 경우

연결되는 포트들의 비트 폭이 서로 다를 수 있습니다. 두 가지 방식으로 처리됩니다.

**1) 기본 동작 (자동 LSB 정렬)**

`col4`(bits)를 비워두면, net은 연결된 포트 중 가장 넓은 폭으로 선언되고, 더 좁은 포트는
그대로(`.port(net)`) 연결됩니다. Verilog 포트 연결 규칙(IEEE 1364/1800)에 따라 시뮬레이터/
합성 툴이 자동으로 LSB 기준 zero-extend(입력 쪽) 또는 truncate(출력 쪽이 net보다 좁은 경우 그
값이 net 전체를 zero-extend해서 구동)를 수행합니다. 예: 8비트 `status` 출력을 32비트
`status_word` 입력에 연결하면 `status_word = {24'b0, status}`와 동일하게 동작합니다.
이 경우 스크립트가 경고를 출력하지만 에러로 중단하지는 않습니다.

**2) 명시적 비트 위치 지정 (`bits` 컬럼)**

LSB가 아닌 특정 위치(예: 32비트 버스의 상위 바이트)에 신호를 놓고 싶다면 `col4`에
`[23:16]`, `[3]`처럼 명시적 part-select를 적어줍니다. 이 값을 쓰는 모든 endpoint(출력 쪽,
입력 쪽 모두)에 동일한 비트 범위를 지정해야 의도한 대로 연결됩니다. 서로 다른 비트
범위를 쓰는 여러 출력 포트가 같은 net을 나눠 쓰는 것(버스 패킹)도 가능하며, 이때 범위가
겹치면 경고가 출력됩니다.

```csv
NET,bus,u_src,lane_a,[7:0]
NET,bus,u_sink,lane_a_in,[7:0]
NET,bus,u_src,lane_b,[23:16]
NET,bus,u_sink,lane_b_in,[23:16]
```

`examples/width_mismatch/`에 두 경우 모두를 iverilog로 검증한 예시가 있습니다.

**3) 버스 패킹: 여러 출력 버스를 모아 하나의 넓은 입력 버스로 연결**

서로 다른(혹은 같은) 인스턴스의 여러 출력 포트를 `bits`로 각각 겹치지 않는 위치에 배치하고,
받는 쪽은 하나의 넓은 입력 포트로 net 전체를 그대로(`bits` 없이) 읽으면 각 출력이 자동으로
해당 비트 구간을 담당하는 다중 드라이버로 조립되어, 입력 쪽에서는 합쳐진 전체 값을 그대로
읽게 됩니다.

```csv
INSTANCE,u_a,sensor_a,,
INSTANCE,u_b,sensor_b,,
INSTANCE,u_sink,packed_sink,,
NET,packed_bus,u_a,temp,[7:0]
NET,packed_bus,u_b,pressure,[15:8]
NET,packed_bus,u_a,humidity,[23:16]
NET,packed_bus,u_b,battery,[31:24]
NET,packed_bus,u_sink,packed_word,
```

`examples/bus_packing/`에서 서로 다른 두 모듈(`sensor_a`, `sensor_b`)의 8비트 출력 4개를
32비트 버스의 각 바이트 레인에 배치하고, `packed_sink`가 이를 하나의 32비트 입력으로 그대로
읽어 `packed_word=44332211`이 나오는 것을 iverilog로 확인했습니다.

### 제한 사항

- `bits`로 지정한 범위와 포트 자체의 폭이 다르면(예: 8비트 포트에 `[15:0]` 지정), 그 부분은
  다시 Verilog의 자동 zero-extend/truncate 규칙을 따릅니다.
- 파라미터화된 폭(예: `[WIDTH-1:0]`)은 숫자로 환산할 수 없으므로, 그런 포트끼리 폭이 다르면
  각 endpoint에 명시적으로 `bits`를 지정해야 하며, 지정하지 않으면 에러로 중단됩니다.
- 포트가 연결정보에 없으면 경고를 출력하고 빈 연결(`.port()`)로 남겨둡니다.

`examples/` 디렉터리에 동작 예시(`cpu_core.v`, `memory.v`, `connections.csv`,
`width_mismatch/`, `bus_packing/`, `unconnected_report/`)가 포함되어 있습니다.
