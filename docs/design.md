# GPT-6 에이전트 설계

이 저장소는 Sol을 총괄·일반 구현·검수에, Luna를 명확한 보조 작업에, Astra를 어려운 구조 문제에 배치한다. 모델별 직접 벤치마크 점수나 지연시간 개선률을 근거 없이 약속하지 않는다. 작업 적합성과 설정 검증은 정적 기준이며, 실제 프로젝트의 비용·시간·품질은 `templates/pilot-results.csv`에 기록한다.

## 역할과 소유권

| 역할 | 모델 | 추론 | 소유권 |
| --- | --- | --- | --- |
| 총괄 | GPT-6 Sol | medium | 요구사항, task card, 계약, 배정, 통합 |
| `token_explorer` | GPT-6 Luna | high | 파일·호출 경로·현재 동작 조사 |
| `token_researcher` | GPT-6 Luna | high | 공식 문서와 버전 근거 |
| `token_worker` | GPT-6 Luna | high | 원인이 확인된 범위 내 작은 수정 |
| `frontend_builder` | GPT-6 Sol | medium | UI 상태·입력·접근성·API 소비 |
| `backend_builder` | GPT-6 Sol | medium | API·인증·검증·업무 로직 |
| `database_builder` | GPT-6 Sol | high | schema·migration·constraint·policy·index |
| `token_verifier` | GPT-6 Luna | high | 지정 테스트·빌드·런타임 증거 |
| `token_reviewer` | GPT-6 Sol | high | 독립 명세 판정과 코드 검수 |
| `frontier_specialist` | GPT-6 Astra | high | 모호한 설계·반복 실패 진단 |

모든 역할은 개인 Codex 홈의 `agents/`에 설치되며, 역할 파일 안에서 재위임을 금지하고 `agents.enabled = false`를 둔다. 상위 세션의 permissions override가 하위 `sandbox_mode`보다 우선할 수 있다. `features.multi_agent_v2`가 `agents.enabled` 설정보다 우선할 수 있으므로 TOML만으로 재위임 도구의 운영체제 수준 제거를 보장하지 않는다.

## 작업 흐름

구조적 기능은 `READY → IMPLEMENTING → VERIFYING → REVIEWING → DONE`으로 기록한다. 총괄이 완료 조건과 허용 경로를 정하고, 공통 API/data contract와 task card의 writer를 지정한다. 공유 작업공간에서는 총괄의 문서 수정도 포함해 writer 한 명만 쓴다.

필요한 경우 DB → 백엔드 → 프론트엔드 순서로 작은 수직 기능을 연결한다. 실행 검증자는 기대값을 맞추려고 제품 코드나 테스트를 수정하지 않는다. reviewer는 실제 diff·기준 SHA·dirty 상태·실행 근거를 읽고 명세 충족과 코드 품질을 별도로 판정한다. 단순 사실 확인과 작은 편집에는 task card를 과도하게 요구하지 않는다.

같은 원인으로 두 번 실패하면 Luna 담당을 Sol 담당으로 바꾸고, Sol에서도 가설이 막히면 Astra 자문을 요청한다. 실패한 작업을 같은 역할에 무한 재시도하지 않는다.

## 설정 병합

`codex/config-fragment.toml`은 전체 설정이 아니다. 설치기는 최상위 모델·컨텍스트·서비스 값과 `[agents]`의 새 키를 기존 문서에 병합하고, 구형 `max_threads`만 제거한다. `job_max_runtime_seconds`를 포함한 다른 agents 키와 플러그인·MCP·인증·알림·신뢰·승인·샌드박스·개발자 설정은 보존한다. TOML 주석과 unrelated table도 보존하도록 `tomlkit`으로 편집한다.

기존 `[profiles.economy]`, `[profiles.deep]`, `[profiles.legacy55]`만 별도 profile 파일로 변환한다. 각각 새 Sol/Luna/Astra 설계값을 적용하고, standalone profile에 있던 알 수 없는 추가 값은 보존한다. 다른 profile table은 config 안에 남긴다. 구형 중첩 profile의 무시되는 `notify` 같은 키는 활성 profile로 승격하지 않으며, 최상위 notify는 그대로 보존한다.

## 백업과 롤백

실제 변경 전에 `CODEX_HOME/backups/gpt6-agents-<timestamp>-<unique>/manifest.json`을 만든다. manifest에는 수정 대상의 상대 경로, 원본 존재 여부와 hash, 새 설치 hash, 원본 bytes 백업이 포함된다. 변경이 없으면 새 백업을 만들지 않는다. 모든 파일은 임시 파일과 `os.replace`로 원자적으로 기록하며, 중간 실패 시 이미 쓴 파일을 이전 bytes로 되돌린다.

롤백은 manifest에 기록된 대상만 사용하고 backup 내부 상대 경로의 traversal을 거부한다. 설치 후 대상 hash가 manifest의 설치 hash와 다르면 사용자 편집으로 보고 복원을 거부한다. 생성했던 파일은 개별 `unlink`하고 디렉터리 재귀 삭제는 하지 않는다.

기존 전역 `CODEX_HOME/AGENTS.md`가 패키지와 다르면 installer는 어떤 파일도 쓰기 전에 중단한다. 사용자가 공통 정책으로 교체하기로 한 경우에만 `--replace-global-agents`를 사용하며, 해당 원본도 같은 백업에 포함한다. dry-run은 이 교체 예정 항목을 표시한다.

## 파일럿

탐색·명확한 수정·수직 기능·독립 검수 각각을 대표하는 작업으로 시작한다. 같은 완료 조건에서 모델과 추론 수준의 영향을 분리해 기록하고, 중대 결함과 권한 누락은 0이어야 한다. 이 기록은 사용자 프로젝트의 관찰값이며, 모델의 보편적 성능 수치가 아니다.

## 참고 문서

- [OpenAI 모델 선택 가이드](https://developers.openai.com/api/docs/guides/model-selection)
- [Codex 서브에이전트 설정](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex 설정 스키마](https://developers.openai.com/codex/config-schema.json)
