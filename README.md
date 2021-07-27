# Grand-Heart-Project 

주요 기능 구현
- AutoEncoder 모델 
- 음식 이미지 데이터 베이스 저장 (되도록이면 Label과 함께)
- 웹 어플리케이션 다자인 (굉장히 어려울 것으로 예상)
- 추천 알고리즘 
  - ML & DL 모델 써보면서 성능 제일 잘 나오는 것으로 선택
  - exponential recovery 적용
- Weighted Sum Algorithm 만들기
- 매칭 시스템
- 주변 맛집 찾아주기

# Futere Plans
|#|To Do List|
|--|--|
|1.|Folium 활용해서 지도로 주변 맛집 뛰우기|
|2.|로그인 기능 & 유저별 데이터 관리|


# 일지
## 강구성
|날짜|한 일|비고|
|--|--|--|
|2021-06-23||개인 추천방식 및 둘 이상의 사용자를 위한 추천방식과 Autoencoder활용을 통한 추천 시스템 회의(+Weighted sum 도입)|
|2021-06-25|기획서(최종) 해커톤 접수 완료||
|2021-07-15|웹 어플리케이션 기본 틀 제작 & 회원가입 및 로그인 기능 구현 & 팔로우 및 언팔 기능으로 타 유저 데이터 접근 기능(데이터베이스만 구축)|현재 POST db를 음식 선택으로 인하여 딕셔너리 형태로 데이터베이스에 유저 데이터를 저장할 수 있는 알고리즘 필요 & 개인 및 2인 이상 유저들의 데이터 생성 기준, 과정 및 조합을 위한 알고리즘, filtering 및 weighted sum 알고리즘 개발 필요, 부가적으로 미니게임 및 웹 디자인 개발 등.|
|2021-07-17|팔로우 및 언팔 기능으로 타 유저 데이터 접근 가능 구현 및 부가 기능||
## 노태윤
|날짜|한 일|비고|
|--|--|--|
|2021-06-19|autoencoder 생성|AIHub에서 한국 음식 이미지 다운 & 간단한 모델 만듦|
|2021-06-23|autoencoder 계속 진행 중.. & 기획서 파트 3 수정|수강증명서 Issue Sharing Submit 완료|
|2021-06-27|autoencoder 50% 완성(?)|찌개 + 구이만 넣고 돌려봄|
|2021-07-16|DB에 넣었을 때 특정 시간 지나면 사라지게끔 구현||
|2021-07-21|선호, 비선호 DB 구현||
|2021-07-27|선호, 비선호 DB 하나의 DB로 통합 <br/> multiple upload 구현 (기현님 코드 참고) 후 모든 이미지 데이터 DB 저장 <br/> 이미지 데이터에서 랜덤 출력 구현 ==> 버튼 클릭시 선호/비선호 DB 저장|Like : 1 <br/> Dislike : 0|
## 김기현
|날짜|한 일|비고|
|--|--|--|
|2021-06-29|웹 페이지에서 이미지 데이터베이스로 저장 및 랜덤으로 화면에 띄우기 구현|우리가 가진 이미지를 데이터베이스에 통합 저장하는 방법 찾아야 함. + 선택하거나 뺀 이미지 정보 다시 나오지 않게 하는 법 구상해야 함.|
|2021-07-26|이미지 다중 업로드 구현|관리자 모드로만 접속 가능한 페이지에서 최초로 음식 업로드 후 기본 데이터베이스로 사용, 선호/비선호 선택 후 데이터베이스에서 제외하고 랜덤으로 계속 음식 나오게 하기.|
