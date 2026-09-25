

##### 모순점(데이터의 부족시 발생할 수 있는) 예외 처리 방법 예시#####

User1_data = {
    '국':11,
    '구이':0,
    '밥':1   
}
User2_data = {
    '국':2,
    '구이':0,
    '밥':0   
}

class User():

  # def __init__(self):
  #   self.sum = 0

  def common(self, user1, user2):
      exception_category=[]
      sum=0
      for key, value in user1.items():
          if value == 0 :
              exception_category.append(key)
      
      for key,value in user2.items() : 
          if value == 0 :
              exception_category.append(key)
      exception_category = list(set(exception_category))
      return exception_category

exception = User()
exception.common(User2_data, User1_data) ## ['밥', '구이'] 제외 될 카테고리

##   두 유저의 공통으로 좋아하는 카테고리가 한 개도 없을 시(겹치는 카테고리가 한 개도 없을 시)
##   또는, Weighted sum 의 결과 값이 가장 높은 카테고리가 여려개 일 경우에도 오류 발생없이 리스트 맨 앞 순서대로 TOP3 출력 가능하게끔 구현




####   Weighted_sum_Algorithm을 두 명의 유저에게 적용 할 경우 예시 #### 
####   Weighted_sum_Base_Algorithm  #### 
User = {
    'User1':{'국':11, '구이':0, '밥':1},
    'User2':{'국':2, '구이':0, '밥':0}
}
  

user1 = [list(list(User.values())[0].values())[i] for i in range(len(list(User.values())[0].keys()))]
user2 = [list(list(User.values())[1].values())[i] for i in range(len(list(User.values())[0].keys()))]

result = [(x + y) * (1 / len(User)) for x, y in zip(user1, user2)]
result ##[6.5, 0.0, 0.5]
top2 = sorted(result, reverse=True)[:2]
for i in top2:
  print(i) # [6.5, 0.5]




#최대 value에 대한 key 찾기(딕셔너리 타입용)
#max(dic,key=dic.get) # di.get 이용
#[k for k,v in dic.items() if max(dic.values()) == v] # 리스트 컴프리헨션 이용



####### User가 새로 추가 되더라도 적용가능한 class 생성 필요, 데이터셋이 어떻게 databse에 저장되어 불러올 수 있는지에 따라서 방법이 바뀔 수 있음. 

















#============================================================================================================================#
# def WSA(i, j):
#     abc = []
#     for i in User:
#         abc = []
#         hum = [list(User.values())[i].values()][i] * (1 / len(User)) + [list(User.values())[i+1].values()][i] * (1 / len(User))
#         abc.append(hum)
#     return abc





# User1_data = {
#     '국':11,
#     '구이':0,
#     '밥':1   
# }
# User2_data = {
#     '국':2,
#     '구이':0,
#     '밥':0   
# }



# def WS_algorithm(User):
#     WS_result = []    
#     WS_result.append({i:User[i] * (1 / len(User))})
#     return WS_result


# WS_result = []
# for i in result:
#     WS_result.append({i:User[i] * (1 / len(User))})

# for i in User:
#     WS_result = User[i]


