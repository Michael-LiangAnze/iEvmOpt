## cfg构建思路

1. 使用ethersolve得到json文件
2. 从json文件获取图关系
3. 使用basicblock作为基础块，在cfg中使用出边表表示图的链接关系



### 部分思路

1. 如何确定起点基本块和终止基本块？
   * 起点基本块的起始偏移量为0，终止基本块的起始偏移量最大



### 函数解释

* Concat(a,b)：把ab两个比特向量进行拼接
* If(exp,a,b)：if exp then a else b