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
    --out top.v
```

- `--rtl`: 서브모듈이 들어있는 `.v`/`.sv` 파일 또는 디렉터리 (여러 개 지정 가능).
  디렉터리를 지정하면 그 안의 `*.v`, `*.sv` 파일을 스캔합니다 (`--recursive`로 하위 폴더까지 스캔).
  각 파일의 포트 목록(ANSI 스타일/구식 스타일 모두 지원)을 자동으로 파싱합니다.
- `--conn`: 연결정보 CSV 파일.
- `--top-name`: 생성될 top 모듈 이름 (기본값 `top`).
- `--out`: 출력 파일 경로 (생략 시 표준출력).

### 연결정보 CSV 형식

`examples/connections.csv` 참고:

```csv
type,col1,col2,col3
INSTANCE,u_cpu,cpu_core,
INSTANCE,u_mem,memory,
NET,clk,TOP,clk
NET,clk,u_cpu,clk
NET,clk,u_mem,clk
NET,addr,u_cpu,addr_out
NET,addr,u_mem,addr_in
```

- `INSTANCE` 행: `col1`=인스턴스 이름, `col2`=서브모듈 이름.
- `NET` 행: `col1`=net(신호) 이름, `col2`=인스턴스 이름(또는 `TOP`), `col3`=포트 이름.
  같은 net 이름을 가진 행들은 서로 연결된 것으로 취급됩니다.
  `col2`가 `TOP`이면 그 net은 생성되는 top 모듈의 외부 포트로 노출되며,
  방향(input/output/inout)과 비트 폭은 연결된 서브모듈 포트에서 자동으로 추론됩니다.

### 제한 사항

- 버스의 일부 비트만 연결하는 bit-slice 연결은 지원하지 않습니다 (net 전체가 동일한 폭이어야 함).
- 같은 net에 폭이 다른 포트가 연결되면 에러로 중단됩니다.
- 포트가 연결정보에 없으면 경고를 출력하고 빈 연결(`.port()`)로 남겨둡니다.

`examples/` 디렉터리에 동작 예시(`cpu_core.v`, `memory.v`, `connections.csv`)가 포함되어 있습니다.
