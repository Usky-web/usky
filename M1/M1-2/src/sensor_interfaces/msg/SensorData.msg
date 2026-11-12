# 虚拟超声波测距消息（接口契约：字段名 / 类型 / 顺序均不可改）
float32 distance              # 距离（米）
string unit                   # 距离单位，固定 "m"
builtin_interfaces/Time stamp # 消息生成时间
uint8 status                  # 0=正常 1=超出量程 2=传感器错误
