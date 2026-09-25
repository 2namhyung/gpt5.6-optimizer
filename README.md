# GPT-6 Codex 에이전트 운영 구성

GPT-6 Sol을 총괄과 일반 구현에, GPT-6 Luna를 범위가 명확한 조사·작업·검증에, GPT-6 Astra를 어려운 설계와 반복 실패 진단에 배치하는 공개용 Codex 구성입니다. 이전 설계의 개인 역할과 프로젝트 역할을 통합해 9개 역할을 모두 `codex/agents/`에 두는 구조로 교체했습니다.

## 구성

메인 기본값은 `gpt-6-sol`의 `medium` 추론이며, 컨텍스트 창은 260,000, 자동 압축 기준은 220,000, 서비스 계층은 `default`입니다. 역할은 다음과 같이 고정합니다.

| 역할 | 모델 / 추론 | 책임 |
| --- | --- | --- |
| `token_explorer`, `token_researcher`, `token_worker`, `token_verifier` | GPT-6 Luna / high | 탐색, 공식 자료 조사, 범위가 정해진 수정, 지정 검증 |
| `frontend_builder`, `backend_builder` | GPT-6 Sol / medium | UI·상태·접근성·API 소비, API·인증·업무 로직 |
| `database_builder`, `token_reviewer` | GPT-6 Sol / high | 스키마·마이그레이션·정책, 독립 검수 |
| `frontier_specialist` | GPT-6 Astra / high | 모호하거나 영향이 큰 설계와 반복 실패 진단 |

한 번에 writer 한 명만 공유 작업공간을 수정하고, 검증과 독립 검수를 분리합니다. 역할 파일은 모두 `agents.enabled = false`와 재위임 금지 지침을 포함합니다. 상위 세션의 permissions override가 하위 `sandbox_mode`를 바꿀 수 있고, `features.multi_agent_v2`가 `agents.enabled`보다 우선할 수 있다는 점은 의도적으로 문서화했습니다. 이 파일은 운영체제 수준의 격리를 보장하지 않습니다.

## 설치

Python 3.11 이상과 `tomlkit==0.15.1`이 필요합니다.

```powershell
python -m pip install -r requirements.txt
python scripts/install.py --codex-home "$HOME/.codex" --replace-global-agents
```

Windows의 기본 경로는 보통 `$HOME/.codex`, macOS·Linux는 `~/.codex`입니다. `--codex-home`을 생략하면 `CODEX_HOME`, 그 다음 `Path.home()/.codex`를 사용합니다. 기존 전역 `AGENTS.md`가 패키지와 다르면 보호를 위해 `--replace-global-agents`를 명시해야 하며, 위 명령은 새 공통 정책으로 교체합니다. 기존 `AGENTS.md`, `config.toml`, 역할 파일, 프로필 파일은 변경 전에 백업됩니다. 설치기는 설정의 플러그인·MCP·인증·알림·신뢰·승인·샌드박스·개발자 설정을 보존합니다.

프로젝트 지침과 작업 템플릿은 명시할 때만 설치합니다.

```powershell
python scripts/install.py --codex-home "$HOME/.codex" --project C:\path\to\project
```

프로젝트 설치는 기존 `AGENTS.md` 안의 표시된 블록만 교체하고 `docs/agent-workflow/`에 없는 task/API/review/pilot 템플릿을 배치합니다. 이미 다른 내용이 있는 템플릿은 건너뛰며, 표시 블록은 반복 설치해도 중복되지 않습니다.

설치 전 결과만 확인하려면 다음처럼 실행합니다. 이 모드는 백업 폴더와 파일을 만들지 않습니다.

```powershell
python scripts/install.py --codex-home "$HOME/.codex" --dry-run
```

백업 목록은 `CODEX_HOME/backups/gpt6-agents-<timestamp>-<unique>/manifest.json`에 기록됩니다. 설치 뒤 사용자가 대상 파일을 편집한 경우 롤백은 보호를 위해 거부합니다. 프로젝트 백업을 되돌릴 때는 같은 `--project`를 다시 지정합니다.

```powershell
python scripts/install.py --codex-home "$HOME/.codex" --rollback "$HOME/.codex/backups/gpt6-agents-20260926-120000-abcdef12"
python scripts/install.py --codex-home "$HOME/.codex" --project C:\path\to\project --rollback "$HOME/.codex/backups/gpt6-agents-20260926-120000-abcdef12"
```

POSIX 셸 예시는 [examples/install.sh](examples/install.sh), PowerShell 예시는 [examples/install.ps1](examples/install.ps1)에 있습니다.
전역 정책 교체가 필요한 경우 PowerShell 예시는 `-ReplaceGlobalAgents`, POSIX 예시는 `REPLACE_GLOBAL_AGENTS=1`을 사용합니다.

## 검증

```powershell
python scripts/validate.py
python -m unittest discover -s tests -v
```

검증은 저장소의 9개 역할, 필수 모델·추론 매핑, config fragment, 공개 문서와 템플릿을 검사합니다. 테스트는 임시 디렉터리에서만 설치·백업·롤백을 시뮬레이션합니다. 모델별 정확도·지연시간·비용 향상률은 이 저장소가 주장하지 않으며, 실제 프로젝트 파일럿에서 측정해야 합니다.

## 파일

- `codex/agents/`: 개인 Codex 홈에 설치할 9개 역할
- `codex/config-fragment.toml`: 기존 `config.toml`에 병합할 기본값과 agents 블록
- `codex/profiles/`: `economy`(Luna), `deep`(Astra), `legacy55` 프로필
- `project/AGENTS.md`: 선택 설치하는 프로젝트 운영 규칙
- `templates/`: task card, API contract, review report, pilot 결과 기록
- `scripts/install.py`: 백업·원자적 설치·안전한 롤백
- `scripts/validate.py`: 로컬 캐시와 개인 환경에 의존하지 않는 정적 검증
- `docs/design.md`: 설계와 운영 근거

## 라이선스

MIT. 기존 저장소의 저작권 표기는 [LICENSE](LICENSE)를 따릅니다.
