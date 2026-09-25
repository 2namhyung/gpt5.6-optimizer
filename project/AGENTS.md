# 프로젝트 에이전트 규칙

<!-- BEGIN GPT6-AGENTS-POLICY -->

- 총괄이 task card, API/data contract, ADR의 owner다. 구조적 기능은 완료 조건과 허용·금지 경로를 먼저 기록한다.
- 공유 작업공간에서 한 번에 writer 한 명만 수정한다. 총괄의 계약 문서 수정도 writer로 센다. 독립적인 읽기만 병렬화한다.
- 필요한 경우 작은 수직 기능을 DB → 백엔드 → 프론트 순서로 연결하고, 실행 검증과 독립 코드 검수를 분리한다.
- reviewer는 실제 diff, 기준 SHA, dirty 상태와 재현 근거를 확인하며 제품 파일을 수정하지 않는다. `VERIFIED`와 `REVIEWED`를 따로 기록한다.
- 기대값을 통과시키려고 제품 코드나 테스트 기대값을 바꾸지 않는다. 미검증 또는 실패한 작업은 `DONE`이 아니다.
- worktree는 DB나 외부 계정 격리를 보장하지 않는다. shared files의 owner를 task card에 명시한다.
- 단순 사실 확인과 작은 편집은 task card를 강제하지 않으며, 운영 DB·배포는 이 세션에서 승인된 범위만 실행한다.

<!-- END GPT6-AGENTS-POLICY -->
