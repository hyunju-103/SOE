# SOE Fiscal Risk Dashboard — GitHub/Streamlit 업데이트 안내

## 기존 데이터와 화면 보존

- 프로젝트 시작 시 기존 8개 SOE의 **데모 포트폴리오**를 그대로 표시합니다.
- 세네갈 Senelec의 실측 데이터는 프로젝트에 포함하지 않았습니다.
- 상단 **Upload data**에서 `tester_Senegal_Senelec_2021-2024.xlsx`를 직접 선택하면 해당 데이터로 전환됩니다.
- 앱을 새로고침하거나 데모 데이터를 다시 선택하면 원래 데이터로 돌아갑니다.
- 9개 메뉴와 기존 계산 방식, 수익성 드롭다운의 기존 항목을 유지합니다.

## 기본 화면부터 제공되는 추가 분석 (업로드 시 데이터 갱신)

1. **KPI Dashboard**: 기존 네 개의 KPI 차트 아래에 매출에 포함된 요금보전액을 제외한 EBIT 마진의 민감도 분석이 나타납니다. 회계적으로 재작성한 실적이 아니라 단순 민감도 계산입니다.
2. **Government Support**: 기존 정부지원/등급 조정 분석 아래에 연도별 요금보전액, 운영보조금, 투자보조금, 자본투입을 구분한 그래프와 표가 나타납니다. 항목을 자동 합산하지 않으므로 중복집계되지 않습니다.
3. **Assumptions**: 업로드된 엑셀의 `Grants_detail`, `Source_lines`, `Validation`, `Checks`, `Definitions`에서 추가 근거와 검사 결과를 표시합니다.
4. **Shock Scenarios**: 관측된 충격 노출 비율이 없을 때 기본 가정값이 사용된다는 안내가 나타납니다.
5. 선그래프는 기존 그래프를 포함해 **모두 부드러운 곡선**으로 표시됩니다. `ADDED` 표시를 하지 않습니다.

## GitHub에 전체 프로젝트 올리기

1. 제공된 ZIP을 **압축 해제**합니다. ZIP 내부 `SOE-main` 폴더의 내용을 확인합니다.
2. 본인의 GitHub Repository에서 **Add file → Upload files**를 선택하고 해당 폴더 안의 파일 및 하위 폴더를 업로드합니다. `Home.py`, `report.py`, `schema.py`, `templates/` 등 구조를 유지하세요. 기존 저장소에 덮어쓸 경우 먼저 원본을 백업하거나 커밋을 남기세요.
3. 변경 사항을 Commit합니다. Streamlit Community Cloud에서는 기존 앱이 `Home.py`를 실행하도록 유지하면 배포가 갱신됩니다.
4. 앱이 열리면 첫 화면의 기존 데모 데이터를 확인한 다음, **Upload data**에서 Senelec 파일을 선택해 추가 분석을 확인합니다.

로컬 실행:

```bash
pip install -r requirements.txt
streamlit run Home.py
```

## 참고

- `.xlsx` 업로드는 기존 앱과 마찬가지로 브라우저에서 외부 SheetJS 라이브러리를 한 번 불러옵니다. 외부 CDN이 차단된 환경이라면 해당 라이브러리의 접근 허용이 필요합니다.
- 파일에 `Data`라는 시트가 있으면 이를 기본 시트로 사용하며, 없으면 첫 번째 시트를 사용합니다.
- Senelec의 `Utility` 업종명은 기존 모델의 `Power / Utilities`로 자동 정규화됩니다.
- 실측 데이터가 부족한 충격 관련 지표는 기존 모델의 업종별 가정이 사용될 수 있으므로 해석에 유의하세요.

## Cost Recovery (KPI Dashboard → Profitability → Ratio)

- **Cost recovery (x)**를 선택하면 기존 Profitability 카드 안에서 같은 연도별 곡선 그래프를 조회할 수 있습니다. 별도 화면이나 그래프는 생성하지 않습니다. Compare across SOEs와 Full scorecard에도 동일 KPI가 적용됩니다.
- 공식: **(Revenues − Government Grants) / (Cost of Goods Sold + Other Operating Expenses)**.
- 엑셀 열 이름 `Cost of Goods Sold`, `Other Operating Expenses` 또는 표준 키 `cost_of_goods_sold`, `other_operating_expenses`를 인식합니다.
- 값이 없는 경우 `Operating Expense`로 대신 추정하지 않습니다. **Cost recovery (x) 선택지는 항상 표시**되며, 필요한 원시 입력값이 없는 경우 그래프 대신 `Data unavailable` 메시지를 표시합니다. 분모가 0 이하이거나 일부 연도만 데이터가 누락된 경우에도 해당 값은 `n/a`입니다.
- `Government Grants`는 **Revenues에 포함된 정부지원금**이어야 합니다. 이미 정부지원금을 제외한 매출액을 넣었다면 이 공식을 그대로 적용하면 이중차감됩니다. PSO/RMA가 `Government Grants`에 이미 포함되었다면 중복으로 추가 차감하지 않습니다. 투자보조금이나 자본투입은 비용회수율의 이 항목에 넣지 않습니다.
- 기준선은 임시 예시로 **alert < 1.00×, good ≥ 1.10×**입니다. 실제 사용에서는 정책 목적과 업종에 따라 보정하세요.
- 기본 데모 원본은 변경하지 않습니다. COGS/기타 영업비용이 없는 기본 데모에서도 **Profitability → Ratio → Cost recovery (x) 선택지는 항상 보입니다**. 이 경우에는 `Data unavailable` 안내가 나타나며 Senelec 엑셀을 업로드하면 자동으로 연도별 그래프를 표시합니다.
- Senelec `tester_Senegal_Senelec_2021-2024.xlsx`에서의 검산: 2021=0.9577×, 2022=0.7627×, 2023=0.9023×, 2024=0.9595×.

## 모든 메뉴와 KPI 항상 표시 (업로드 불필요)

- 상단 9개 메뉴는 기본 내장 데모 데이터로 시작할 때부터 항상 조회할 수 있습니다. 현재 선택한 탭 외에 숨겨진 HTML 섹션은 통상적인 탭 전환 동작이며 메뉴를 삭제하는 것이 아닙니다.
- KPI Dashboard의 네 카테고리(Profitability, Liquidity, Solvency, Fiscal dependency) 드롭다운은 **등록된 모든 지표를 항상 제공**합니다. 기본 데이터에 원시 입력값이 없어도 Cost recovery 등 조회할 수 있습니다. EBITDA margin은 이전 요청에 따라 등록 목록에서 제외한 상태를 유지합니다.
- 필요한 원시 데이터가 없으면 해당 차트 영역에 **Data unavailable**을 표시하고 누락 필드를 안내합니다. 결측을 0으로 가정하지 않으며, 실제 데이터가 부족한 지표는 포트폴리오 위험 점수 계산에서 제외합니다.
- KPI 전체 Scorecard의 분류 메뉴와 표 열도 상시 조회됩니다. 값이 없는 칸은 n/a로 유지하며 알림 건수에 임의 포함하지 않습니다.
- 추가 정부지원 그래프와 근거 패널의 자리도 항상 표시합니다. 신규 데이터 업로드 시 같은 화면에서 값만 갱신합니다.

## 유가 충격: 현금흐름·정부 보상금·전기요금 정책 (Shock Scenarios)

SENELEC 리뷰 노트의 내용을 반영했습니다. 유가 충격은 비용만 늘리는 것이 아니라, 지금 내야 하는 연료비와 나중에 들어오는 정부 보상금 사이에 현금 공백을 만들고, SOE는 이를 차입으로 메웁니다.

- **Fuel 탭**: *End-user tariff increase*(Option A = 0% 동결, Option B = +10~15%)와 *State compensation share (Case C)*. Case C는 요금 인상 후 남은 연료비 증가분 중 정부가 보상하는 비율입니다(SENELEC의 경우 RMA와 요금 수입의 차이, 100% = 정부가 전액 보상).
- **Cash & financing 탭**(신설): 정부 보상금의 당해 지급률(300일 지연 ≈ 18%, 리뷰 노트는 30%), 미지급분의 다음 해 회수율, 미지급분 손실 처리 비율(100% = "미지급분을 손실로 처리"하는 방식), 현금 부족분 중 단기 조달 비율과 그중 공급업체 미지급 비율, 신규 차입 이자율, 환급받지 못하는 매입 VAT 비율.
- **프리셋**: "Oil +60% with delayed State payment"(`config.OIL_SHOCK_PRESET`), "Option A: tariff freeze", "Option B: +10%", "+15%". classic(Python) 화면에서는 탭 위의 스위치로 켭니다.
- **Liquidity & State compensation 카드**(신설): 정부 보상 인식액·현금 지급액·미지급액(최대치), 현금 부족분·신규 단기차입·공급업체 미지급·이자, 유동비율·조정 유동비율(정부 미수채권·VAT 제외)·부채자산비율, 누가 부담하는지 보여주는 막대그래프, 연도별 표. 시나리오 CSV에도 같은 열이 들어갑니다.
- **선택 데이터 열**: `Government Arrears Owed`는 기초 정부 미수채권, 새 열 `VAT Credits`는 기초 미환급 VAT로 읽고, 둘 다 조정 유동비율에서 뺍니다.

- **Cash waterfall (개혁, 기본값 꺼짐)**: Cash & financing 탭의 On/Off 스위치 또는 프리셋 줄의 "+ Cash waterfall (reform)" 버튼. 수입을 보호 계좌(SENELEC의 FSE)에 모으고 IPP에 먼저 지급하는 구조입니다. 모델에서는 (1) 첫 전망연도에 단기 은행차입(`Short Term Debt` 열, 없으면 near-term maturity share × 총부채)의 설정 비율을 장기 대출로 차환해 유동부채가 줄고(총부채는 그대로) X1이 오르며, (2) 당좌차월 금리(기본 8%, 노트의 7.5~8.5%)와 장기 금리(기본 5%, 임시값)의 차이만큼 매년 이자가 절감되고, (3) 공급업체 미지급이 생기지 않습니다(이후 현금 부족분은 위에서 정한 단기/장기 비율과 금리의 은행차입). Liquidity 카드에서 같은 시나리오를 개혁 전후로 비교합니다(Z-EM·등급·유동부채·유동비율·EFC).
- **긴급 정부지원**: *Borrowing cap before emergency support*(부채/자산 상한, 0 = 꺼짐). 연말 총부채/총자산이 상한을 넘는 만큼은 차입하지 못하고 정부가 자본으로 투입합니다(`Emergency Support`, EFC와 별도의 재정 지출). IMF SOE 스트레스 테스트의 조달 순서(현금 → 차입 → 정부 투입)의 마지막 단계입니다.
- **RMA 대비 고객 부담 비율**(`Tariff Share of RMA`): (수입 − 정부보조금 + 요금 인상분 + pass-through) / (수입 + 연료비 증가분). Option A에서 고객 징수가 충격 후 RMA의 몇 %를 메우는지 보여줍니다. `Government Grants`가 없으면 표시하지 않습니다.

**결과를 읽을 때:** 미수채권을 단기차입으로 메우면 유동자산과 유동부채가 같은 금액만큼 늘어서, 1 미만인 유동비율은 오히려 오를 수 있습니다. 보상금이 수익으로 잡히는 동안 순이익과 Z-EM은 거의 움직이지 않고, 충격은 현금·단기차입·조정 유동비율·정부 미지급액에서 드러납니다. 미지급분을 손실로 처리하면 Z-EM이 움직입니다.

**기존 결과와의 관계:** 새 설정이 모두 기본값이면 기존 결과와 같습니다(`tests/check_cash_channel.py`로 확인). 예외는 손실을 차입으로 메운 해에 총자산이 더 이상 줄지 않도록 재무상태표를 맞춘 것 하나입니다. 데모 포트폴리오의 standard stress에서는 zone·등급·EFC·조기경보 결과가 그대로이고, 손실 SOE의 Z-EM 값만 덜 음수가 됩니다(SOE A 최종연도 −16.5 → −9.3). 기존 숫자가 필요하면 `config.py`의 `DEFAULT_SHOCK_PARAMS["legacy_loss_assets"]`를 `True`로 바꾸세요.

**가정 확인 필요:** 신규 차입 이자율 8%는 임시값입니다. 연료비 비중 70%에 IPP 구매비 중 연료 연동분이 포함되는지 확인하세요.

검사:

```bash
python tests/check_engine_parity.py   # JS 엔진과 Python 결과 비교 (Node.js 필요)
python tests/check_cash_channel.py    # 현금 채널: 기존 결과 재현, 재무상태표 항등식, 현금 계산
python tests/check_cash_waterfall.py  # cash waterfall, 차입 상한/긴급 지원, RMA 비율 (기본값 꺼짐 = 기존 결과와 동일)
```
