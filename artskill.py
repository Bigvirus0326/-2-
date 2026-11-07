"""카드 원화 구도 설계 스킬 (사용자 제공 SKILL.md). AI 이미지 설명서의 카드 삽화 부분에 그대로 들어간다.
앱 폴더에 card_composition_skill.md 가 있으면 그 파일을 대신 쓴다."""

SKILL_MD = r"""---
name: sts2-card-composition
version: 1.0
language: ko
summary: 슬레이 더 스파이어 2 계열의 전투 카드 원화를 위한 구도 설계 및 이미지 생성 프롬프트 스킬. 카드 프레임이 아닌 일러스트 원화에 적용.
---

# 카드 원화 구도 설계 스킬

## 목적
카드 이름·효과·직업·주요 시각 요소를 바탕으로 **작은 크기에서도 행동이 즉시 읽히는 정사각형 카드 일러스트**를 설계한다. 기준은 Slay the Spire 2 카드들의 대표적인 시각적 경향에서 추출한 **구도 원칙**이며, 특정 카드의 이미지를 그대로 복제하지 않는다.

## 적용 범위
- 적용: 카드 아트의 카메라, 원근, 크롭, 실루엣, 피사체 우선순위, 동작 방향, 이펙트, 배경 밀도.
- 별도 지시가 없는 한: **1:1 정사각형 / 원화만 / 카드 테두리·UI·코스트·제목·텍스트 제외**.
- 특정 화풍(채색법·선화 등)은 별도 스타일 스킬 또는 사용자 지시에 맡긴다. 이 스킬은 **구도가 우선**이다.

## 입력 정보
필수: `카드명`, `카드 효과 또는 표현하려는 행동`.
선택: `직업/세계관`, `등장 인물 또는 물체`, `공격/스킬/파워`, `대표 색상`, `금지 요소`, `스타일 레퍼런스`.
정보가 부족하면 설명 가능한 시각적 해석을 한 가지 선택해 진행한다. 카드 효과에 없는 설정·캐릭터를 무리하게 만들어 넣지 않는다.

## 작업 절차
1. **의미 압축:** 카드 설명에서 동사 하나(베기/방어/시전/소환/축적/폭발 등)와 시각적 명사 하나(검/손/방패/번개/빛/문양 등)를 뽑는다.
2. **주제 선택:** 인물·신체 일부·무기·마법 이펙트·상징물 중 **주 피사체 하나**를 선택한다. 필요할 때만 보조 피사체 하나를 더한다.
3. **구도 선택:** 아래 6가지 유형 중 하나를 기본값으로 정한다. 장면이 복잡해지지 않는 선에서 보조 유형 한 개까지 조합 가능.
4. **카메라/크롭 지정:** 시점(로우 앵글/3/4뷰/탑뷰 등), 거리(클로즈업/상반신/전신), 전경·중경·후경을 명시한다.
5. **동선 설계:** 시선이 `가장 큰 실루엣 → 행동의 접점/이펙트 → 보조 요소` 순서로 흐르도록 한다. 필요하면 대각선·호형 궤적을 이용한다.
6. **배경 단순화:** 장면 의미를 알리는 최소한의 배경만 남긴다. 배경을 묘사하기보다 색면·그림자·속도선으로 주제를 분리한다.
7. **출력:** 제작용 구성 요약 + 영어 이미지 생성 프롬프트 + 네거티브 제약 + 간단 검수.

## 구도 유형 라이브러리

### A. 근접 타격 / Foreshortened Impact
- 적합: 강타, 베기, 찌르기, 돌진 공격.
- 주 피사체: 주먹·칼날·창끝·타격 순간의 무기.
- 카메라: 로우 앵글 또는 3/4뷰, 강한 단축법(foreshortening).
- 배치: 무기/손이 화면 전경을 크게 차지하고 몸통은 뒤로 작아진다. 공격 방향에 대각선 리듬.
- 피해야 할 것: 먼 거리의 작은 전신, 표정 위주의 인물 소개샷.

### B. 동작 실루엣 / Dynamic Action Silhouette
- 적합: 연속 타격, 회피, 점프, 검무, 기동.
- 주 피사체: 읽기 쉬운 상반신 또는 전신 동작.
- 카메라: 3/4뷰, 비스듬한 자세와 넓은 액션 아크.
- 배치: 머리·팔다리·무기가 서로 겹쳐 뭉개지지 않게 실루엣을 분리한다.
- 피해야 할 것: 팔다리가 뒤엉킨 불명확한 포즈, 지나친 군중.

### C. 능력 시전 / Focused Casting
- 적합: 마법, 회복, 방어막, 버프, 상태 적용.
- 주 피사체: 펼친 손, 마법진, 광원, 보호막의 접점.
- 카메라: 손 또는 시전 위치 클로즈업; 인물은 일부만 노출 가능.
- 배치: 밝은 효과 한 지점을 중심으로 주변에 짧은 방사선·고리·흐름을 배치.
- 피해야 할 것: 복잡한 풍경, 얼굴이 효과를 가리는 구도.

### D. 상징물 강조 / Isolated Symbol
- 적합: 장비, 준비, 자원 획득, 특수 능력, 개념적 효과.
- 주 피사체: 칼·방패·고서·룬·유물·에너지 구체.
- 카메라: 클로즈업, 중앙 또는 비대칭 배치.
- 배치: 상징물의 외곽선을 선명하게 하고 주변에 공간적 여백.
- 피해야 할 것: 설명하려고 여러 소품을 나열하는 것.

### E. 상태 연출 / Character-State Tableau
- 적합: 자세 유지, 반격 태세, 집중, 중독, 지속 버프·디버프.
- 주 피사체: 몸의 자세 + 상태를 드러내는 하나의 효과.
- 카메라: 상반신 또는 3/4인물, 효과가 신체에 연결되는 모습.
- 배치: 표정만으로 설명하지 않고 피부·장비·손 주위의 명확한 상태 효과를 보여준다.
- 피해야 할 것: 정면으로 선 캐릭터 초상화만 그리는 것.

### F. 추상 이펙트 / Graphic Energy Burst
- 적합: 광역기, 폭발, 번개 연쇄, 충격파, 에너지 소비·방출.
- 주 피사체: 이펙트의 시작점 또는 폭발 중심.
- 카메라: 중심 폭발, 사선 분출 또는 위에서 내려다보는 확산 구도.
- 배치: 굵은 에너지 흐름 1~3개를 중심으로 큰 형태가 먼저 읽히게 한다.
- 피해야 할 것: 화면 전체에 균등한 파티클, 주목할 곳 없는 시각적 소음.

## 카드 종류에 따른 기본 선택
- 공격: A 또는 B, 광역 공격은 F.
- 스킬: C 또는 D, 방어·반격 태세는 E.
- 파워: D 또는 E, 에너지가 분출되는 콘셉트는 F.
- 단, **카드 종류보다 실제 카드 효과를 우선**한다.

## 구도 강제 규칙
1. **한 장면, 한 핵심 사건**. 순차적 동작을 여러 컷으로 나누지 않는다.
2. **주 시선 집중점 하나**. 가장 큰 피사체/가장 높은 대비/가장 선명한 디테일이 서로 다른 지점을 가리키지 않게 한다.
3. 작은 축소 이미지에서도 `무엇이 / 어떻게`를 구별할 수 있도록 크롭과 실루엣을 과감하게 잡는다.
4. 전신은 반드시 필요한 카드에서만 선택한다. 손, 무기, 상체만 보여줘도 된다.
5. 대각선은 선택 사항이지 필수 공식이 아니다. 정적인 카드에는 상징물의 단독 배치와 여백을 허용한다.
6. 인물 없이도 전달 가능하면 도구나 마법 효과만으로 구성한다.
7. 가독성을 해치는 복잡한 배경·장식·미세 패턴을 줄인다.
8. 한 카드의 원화 내부에 텍스트, 카드 프레임, 비용 숫자, UI를 생성하지 않는다(별도 요청 제외).
9. 원본 게임의 특정 카드 일러스트를 그대로 재현하지 않고 **구도 문법만 참고**한다.

## 생성 프롬프트 작성 형식

**구성 요약**
- 동작/메시지: [한 문장]
- 유형: [A~F]
- 주 피사체: [하나]
- 카메라/크롭: [앵글·거리]
- 동선/초점: [시선 흐름]
- 배경: [색상과 단순화 방식]

**영어 이미지 생성 프롬프트**
```text
Square 1:1 standalone card illustration artwork (art only, no card frame or text).
Subject: [single focal subject and defining action].
Composition: [A-F composition translated into camera, crop and perspective]; [foreground/midground/background relationships].
Motion and focus: [clear action direction, focal point, distinctive silhouette, readable contact or energy origin].
Environment: [simplified abstract or minimally indicated background], strong separation of subject and background.
Color and lighting: [limited palette, deliberate contrast, strongest accent at the focal action].
Ensure the image remains legible as a small gameplay card thumbnail.
[Additional art-style instructions supplied by the user].
```

**네거티브 제약**
```text
No card border, UI, title, mana cost, lettering, watermark, multi-panel layout,
excessive scenery detail, cluttered props, tiny distant subject, ambiguous action,
multiple competing focal points, generic centered character portrait.
```
> 참고: 정적인 상징물 카드에서는 'generic centered character portrait'만 제한하며, 의도적인 중앙 상징물 구도는 허용한다.

## 적용 예시 (메이플스토리 모험가 카드)

### 히어로 / 브레이브 슬래시
- 의미: 거대한 검격 1회.
- 유형: A + B.
- 구성: 오른쪽 아래에서 왼쪽 위를 가로지르는 검날이 전경을 지배한다. 검을 쥔 손과 어깨만 노출해 충격 직전의 순간을 표현. 배경에는 단순한 붉은 속도선.
- 프롬프트 핵심: `extreme foreshortening, oversized foreground blade, diagonal slash arc, cropped sword arm, clear single impact direction`.

### 비숍 / 프레이
- 의미: 자신을 포함한 아군의 피해를 증폭하는 신성한 지원 효과.
- 유형: C + F.
- 구성: 화면 아래쪽의 펼친 손에서 하나의 밝은 문양이 형성되고, 문양에서 여러 방향으로 빛의 줄기가 퍼짐. 필요 이상으로 여러 인물을 넣지 않음.
- 프롬프트 핵심: `close-up casting hands, radiant sacred sigil, one concentrated luminous origin, outward rays representing team-wide empowerment`.

### 아크메이지 / 체인 라이트닝
- 의미: 번개가 연쇄적으로 이동.
- 유형: F.
- 구성: 화면을 지그재그로 관통하는 굵은 번개 1줄기와 2개의 가지. 굵은 주 경로가 먼저 보이게 구성. 시전자는 손끝만 노출 가능.
- 프롬프트 핵심: `single dominant zigzag lightning path, two secondary branches, dynamic depth, minimal background, strong high-contrast electric glow`.

## 최종 검수 (생성 전/후)
- [ ] 그림을 작게 봐도 주제와 행동이 1초 안에 구분되는가?
- [ ] 초점 하나가 압도적으로 분명한가?
- [ ] 선택한 구도 유형과 카메라/크롭이 명시됐는가?
- [ ] 주 피사체의 외곽선이 배경과 분리되는가?
- [ ] 배경 장식이 동작과 이펙트를 방해하지 않는가?
- [ ] 캐릭터 정면 전신샷이 무의식적 기본값이 되지 않았는가?
- [ ] 카드 프레임·텍스트·UI가 없는가?

검수 실패 시, 디테일 추가보다 **피사체 확대 → 크롭 재설계 → 배경 단순화 → 초점 재집중** 순서로 수정한다.
"""
