# iEvmOpt

[TOC]

### 构建函数的cfg

#### CODECOPY指令

codecopy指令用于将运行时的代码段+数据段复制到memory中，因此，修改了原来的字节码之后，需要修改codecopy指令中的偏移量和size。因为size可能会变大，导致原来的位置中无法填入新的size，因此好需要做重定位。

### 函数识别以及路径搜索

#### 前提假设

* 同一个函数内的指令的地址都是从小到大连续的
* 我们不关心函数调用关系产生的“错误的环”，因为这种错误的环我们可以在搜索路径时，可以通过返回地址栈解决掉。

#### 基本原理

找到某个函数的调用时的调用边和返回边，从而解析出函数的所有funcbody节点。紧接着，对函数内的所有节点，分析是否存在环即可。如果存在就把他们收缩成一个点，并标记为loop-related。在寻找所有从init到invalid的路径时，不走这些节点即可。

###### 3.13更正

这些节点也要走，不然不能遍历出一个invalid节点的所有路径。

同时，环形函数调用链的点也要走。

解决这两个问题的方法为：一旦走入一个函数内连通分量的点，或者环形函数调用链相关的点，就将其访问状态标为true；当离开的时候，将其访问状态标为false。原因是，一旦这些点正在被访问，则其只能走一次，否则会出现死循环。

路径中包含未被识别的函数的节点时，该invalid节点会被放弃优化，因为无法确定这些未识别的节点是否存在环形结构等。

###### 3.24更新

不做函数scc的压缩，只进行标记，因为后续要做重定位。

###### 3.26更正

环形函数调用链并不能被优化，因为jump边的信息会找不全。一旦检测到环境函数调用链的情况，马上退出优化。

###### 4.15更新

scc相关节点，不一定只走一次，而是说对于某一个函数调用链，只能走一次。

不检测环形函数调用链的情况，只检测递归的情况



#### 一个简单粗暴的解决方法

找出图中所有的unconditional jump边。它们出现的原因包括：

* 函数的调用
* 函数的返回
* for、while循环结构
* 除以上原因外的其他原因

每一次函数的调用，必将伴随一次函数的返回。因此，一个函数的调用边必然和一个函数的返回边相匹配（这是我们理想的情况，实际上会有反例的，详见后面的特殊情况2）。于是我们可以假设每一条unconditional jump边(地址a---->地址b)：

* 可能是调用边。调用的起始地址为：地址a；返回地址为：a+1
* 可能是返回边。调用的起始地址为：地址b-1；返回地址为：b

这样，我们便得到了一个四元组，它可以表示为`(a,a+1,b-1,b)`。

当我们得到图中所有的四元组之后，剩下的问题，就是拿他们配对(一次调用必然引起一次返回)。做一个两层的for循环进行遍历，当我们取到两个四元组：A、B时，这样判断：

* 如果A[0] == B[2] and A[1] == B[3] ，则A是调用边，B是返回边。匹配成功
* 否则，匹配失败

匹配成功之后，如何得到一个funcbody内的所有节点？我们取出其中任意一个四元组，从调用边的终点开始做dfs，然后只走起始offset位于`[调用边指向的block的起始offset，返回边起始block的起始offset]`的节点，这样便能找到所有的funcbody节点。

#### 特殊情况以及解决方案

###### 1.在循环里面进行函数调用

函数代码大概是这样，在一个for循环里对另一个函数进行调用

```
pragma solidity ^0.4.0;

contract test2{

    function g()private returns(uint){
        return 1;
    }


    function f()public returns(uint){
        uint i = 0;
        uint sum = 0;
        for (;i < 5;i+=1)
            sum += g();
    }

}
```

得到cfg如下图所示。此时看cfg，会有两个问题：

* 图中会有一个环，这个环应当被压缩为一个点。但是如果只看同一个函数内的点的话，并不能分析出这个环，所以说需要添加一条辅助的边（其实这就是沈学长说的fall边，ethersolve没有给出而已）
* 从起始offset为108的block开始，做dfs，只走函数内的点，直到offset为149的点结束。此时如果没有蓝色的边的话，就不能找到offset为135的块。

![](D:\Projects\iEvmOpt\pics\1.png)

解决办法也很简单。在做完所有的jump边的匹配之后，给它们的调用者加上一条辅助边即可。再做完这一步之后，再去寻找每个函数内的节点，以及环的处理。

###### 2.多层函数调用(会终止)

代码大概是这样的：(f->g->h)

```
pragma solidity ^0.4.0;

contract test2{

    function g(uint x)private returns(uint){
        return h(x - 1);
    }

    function h(uint x)private returns(uint){
        if (x > 10)
            return f(x - 1);
        else 
            return 0;
    }

    function f(uint x)public returns(uint){
        return g(x - 1);
    }

}
```

编译得到的cfg如下。我尝试对其使用该算法，结果发现起始offset为142的block会被归类为两个不同的函数（看颜色，第一个函数是红的，第二个函数是蓝的）。事实上，一旦函数调用链的长度大于2，这个问题必将产生。

![](D:\Projects\iEvmOpt\pics\2.png)

解决办法很简单，我们需要再加一条假设，它包含这两点：

* 任何函数调用的起始边，必然是伴随这样两条指令产生的：`PUSH 返回地址;JUMP`
* 任何函数调用的返回边，必然不是这样的结构：`PUSH 返回地址;JUMP`。

这样一来，我们就能确定哪些边有可能是起始边，哪些边必然不是起始边。这样便能排除错误的情况。

4.21特殊情况：因为有的调用边不是通过push jump来实现的，如AND JUMP，这样的边也会被怀疑是调用边。这样一来，问题又会复现。因为这种情况很少，因此做以下限制，尝试找全所有函数：

* 调用边指向的点的offset必须小于返回边起始点的offset（对于上例无效
* 从起始节点开始走dfs，直走偏移量位于函数范围之内的节点，必须能走到终止节点，且找全函数的所有节点（对于上例有效
* 找到的所有函数节点，不能是已经赋值为某一个函数的节点



###### 3.环形函数调用链

在使用dfs进行寻路时，因为某一个函数可能被多次调用，因此不能使用visit数组进行计数。此时，一旦出现环形函数调用的情况，如f->g->h->f .....，因为我们是在图的基础上做分析的，并没有函数实际执行时的上下文信息，因此该环会永远执行下去。

解决的办法也很简单:

* 一旦发现一条调用边，在决定是否走这条边时，先检查返回地址是否已经push到栈内，如果存在则不走这条边。原因是，如果返回地址已经在栈内，意味着该函数已经被调用过，不能再次调用，否则会无限循环。

注意，环形函数调用的环当中的assertion也是不做优化的，因为在做路径搜索的时候，不知道该环在什么时候会终止。

检测方法为：

* 同上，一旦检测到栈中存在返回地址，则将两次返回地址之间的所有函数的所有节点，标记为loop-related。

  

###### 4.函数返回边特殊处理

一旦遇到一条返回边，要先保存当前函数返回地址栈的副本。在做完返回边终点的dfs操作之后，要检查当前函数的返回地址还在不在栈顶。因为如果返回边走曾经走到过终止节点，则函数返回地址栈的信息会被清空，包括之前的函数调用，此时需要重新设置回原来的栈信息。





###### 4.递归调用出现的未知错误

因为递归的出现，cfg无法被正确地解析。如下图所示，157处出现了函数调用，但是158处的block并没有入边：

```
pragma solidity ^0.4.0;

// 用于测试递归调用情况
contract test7 {


    function fibonacci(uint a) public returns(uint){
        assert(a > 0);
        if(a > 2)
            return fibonacci(a-1)+fibonacci(a-2);
        else
            return 0;
    }

    function f2() {
        uint res = fibonacci(10);
    }
}
```

<img src="D:\Projects\iEvmOpt\pics\test7_cfg.png" style="zoom: 50%;" />

此时，压缩函数体内的连同分量，就会把函数头结点也压缩进去。后续在做路径搜索时，不会走这个函数。

检测这种情况也很简单，判断函数头结点有没有被压缩即可

###### 5.实际上并不会走的路线

因为在路径搜索的时候，并没有函数执行的上下文。实际在函数运行的过程中，有些路径虽然已经被搜出来，但是并不会被执行(jumpi的判断值为恒定的true或者false，并不会出现两条路随便走一条的情况)。这时候，需要在符号执行的过程中进行判断，判断当前路径的合法性。一旦发现一条路径是不合法的，则直接将可达性置为false，后续不用求解器做check。



###### 6.经过计算的跳转地址

在特殊情况2中，添加了新的假设：

* 任何函数调用的起始边，必然是伴随这样两条指令产生的：`PUSH 返回地址;JUMP`
* 任何函数调用的返回边，必然不是这样的结构：`PUSH 返回地址;JUMP`。

但是实际上，在做函数调用时，不一定就是这样开头，有可能会对跳转地址进行计算。为了能正确解析出结果，现在添加一个新的方法：

* 在每个block内部，进行tagStack执行，看最后做Jump的时候，地址是否是由该block push的
* tagStack执行的基本方法，与evmopt一致
* 为了防止stack的大小出现问题，在做执行之前，先在stack中push进16个None
* 这样的方法，运用了一条假设：block的跳转地址，必须只能在一个block内完成





### 约束收集与求解

#### 路径分类

#### 约束求解

给定一个假设：所有的invalid节点都是通过jumpi跳转进入的。因此只需要收集每次jumpi的condition，并加入求解器即可。



### 完全冗余的优化

#### 基本假设

* 要进入invalid节点，必然通过jumpi。其中jumpi判断false则跳转到invalid，判断true则跳转到invalid的下一个地址。
* dispatcher中的内容不能被修改。

#### 算法思路

完全冗余的优化过程大致如下：

1. 生成支配树
2. 取出一个invalid节点，取出其中一条函数调用链，随意指定其中一条路径，开始做符号执行，并记录路径上各个地址的程序状态
3. 在支配树中，从invalid节点开始向根出发，找到程序状态相同的最远的地址，这个地址到invalid节点之间的序列便是assertion相关的序列
4. 为了不影响其他未做优化的完全冗余assertion，此时在assertion相关的序列中，使用自定义的空指令0x1f进行替换



### 部分冗余的优化

#### 基本假设

与完全冗余相同

#### 算法思路

部分冗余的优化过程大致如下：

1. 删除原来虚拟的exit block，方便添加新的函数体
2. 



### 重新构造字节码

在进行了完全冗余和部分冗余之后，会删除或者增加一些block，因此需要重新构造合约的字节码。具体方法如下：

* 在做部分冗余和完全冗余的优化时，将相关的指令序列置为空指令1f
* 最后做完所有的优化之后，将所有block的字节码拼接起来，除去其中的空指令，便能得到需要的指令序列





### 重定位

对一个block，在做完冗余优化之后，它的变化可能是：

* 掐头：开头的jumpdest被删除了
* 去尾：从assertion相关的节点开始，都被删除了
* 掐头去尾：以上两种情况的结合



#### 需要获取到的信息

* 何处的jump/jumpi

* 在何处进行跳转地址push

* 跳转地址在push时，push了几个字节

* push的地址是多少/跳转的目的地是哪一个block

  

#### 基本思路

在做完所有的冗余优化之后，将字节码按照block的offset，尝试拼接在一起。然后再对上面提到的每一条信息进行“试填入”。

解释一下为什么需要试填入：对于地址重定位，新地址的字节数可能和原地址不一样，如果新地址更长，则需要在原来的地方多push一些字节，增加block的字节数；对于字节码信息的修改，因为修改之后函数体的长度发生了变化，如果函数体的长度增加，则在codecopy的时候，新size会遇到一样的问题，因此需要试填入。

试填入阶段，一旦字节数发生了变化，则整个过程都需要重新进行计算。



#### 算法

1. 将跳转信息去重
2. 根据删除区间信息，将位于删除区间之内的跳转信息删除
3. 对每一个block，根据删除区间信息，删除对应的指令，并记录下旧地址到新地址的映射
4. 根据jump信息中的push出现的位置，对跳转信息进行升序排序。这样做的目的是：一旦出现试填入失败的情况，方便修改地址映射关系。
5. 进行试填入：
   1. 取出一条push信息，尝试将其填入原来的位置
   2. 如果该信息可以填入，则直接进行填入
   3. 一旦遇到某一条跳转信息，它的新内容不能填入到旧位置，则要在这个push的位置开始，将后面的所有字节码都整体向后移动一个单位。这时候，地址映射会重新进行计算：位于该push之前的地址映射，都不需要进行计算；位于该push之后的地址映射，新的地址值会加上移动的偏移量。计算完毕之后，并不会填入新地址，而是开始新一轮的试填入，新地址会在新一轮的试填入中得到填入
   4. 直到所有的跳转信息都能顺利填入之后，试填入结束
6. 重新生成所有的block信息，并将block中的字节码拼接成新的函数字节码



### 关于codecopy

#### 前提

只能对两种类型的codecopy进行优化：

* 在constructor中的，用于将运行时字节码复制到memory中的codecopy
* 在任意地方的，但是只是用于获取数据段的codecopy

对于其他用法的codecopy，一旦被检测到，就会拒绝优化该字节码。 



#### 基本算法

1. 在路径搜索的时候，使用tagstack获取codecopy信息
2. 对codecopy信息进行去重
3. 因为codecopy在做填入的时候，offset和size不一定可以填入原来的位置，因此需要重复做和重定位一样的过程。为了简化代码，这里直接将codecopy信息转换成跳转信息，然后在重定位的时候，同时对两种信息进行处理。

#### 一些坑

codecopy的size可能是整个字节码的长度

### 4.11新思路

将新构造的函数体放在原来的函数体后面，而不是数据段的后面。



### 一些坑

#### codecopy的奇怪size

test15，运行时的字节码，除去运行时的代码长度之后，还剩余一段，这一段与remainingdata并不相同。即constructor中的codecopy，size不一定等于运行时代码段+数据段的长度。

#### 一个scc可能要多次进行遍历

AnxToken里，如果一个scc内的节点只走一次，则无法遍历所有的节点

#### SHA3改内存

SHA3可能会改内存，因此如果出现路径上有SHA3指令的话，获取程序状态时，不要memory的部分。例子如下：

```
//0x1fD4fd5B079ab1eDA7F08719737FF61945289aEf
assert(balanceOf[_from] + balanceOf[_to] == previousBalances)
```

其中的previousBalances为局部变量，另外两个是mapping后的结果。字节码首先是用dup1来获取previousBalances，然后再获取其他两个参数。其中用到了sha3，于是会用一系列的mstore来该内存，这种状态改变一直持续到invalid。最后拿着invalid的程序状态去找，并不能找到dup1时的状态，因为dup1处还没有改过内存。

#### 有的函数确实会没有出边

以下函数，是没有返回边的

```
    //0x022e063958a870c345749d1fe32f7e7bf2d240ed
    function moveBrickClear() onlyOwner public {
        require(msg.sender == owner, "only owner can use this method"); 
        selfdestruct(msg.sender);

    }
    
    //0xE0339e6EBd1CCC09232d1E979d50257268B977Ef
    function initialize(bytes calldata /*data*/)
        external pure
    {
        revert("CANNOT_CALL_INITIALIZE");
    }
```

调用者节点的后一个节点，是没有入边的，这个节点的结构是：jumpdest;Stop

为了解决这个问题，现做一个新的假设：

* 假设类似的函数会出现，它们都没有返回边，而是直接走向了程序的终止节点
* 但是因为编译器会为他们保留返回地址，因此会在调用这些函数之前，会在调用者节点push返回值

为了找出这些函数，只能在找出常规函数之后进行。具体方法如下：

* 在找出常规函数之后，在函数的调用边起始节点和返回边终止节点之间加边
* 找出所有的形如JUMPDEST；STOP的节点，用以备用。同时，它们必须是全部的，没有入边的节点。若不能覆盖所有没有入边的节点，则要放弃优化
* 对原图中所有的节点排序
* 对上述找出的节点，查找比他们offset小的第一个节点。如果这个节点里面出现了对应的push addr;jump，则说明是可能的调用节点。同时检查是否push过返回地址
* 从可能的调用节点开始，在排序好的节点中一直找，直到找到exit block或者一个已经被标记为函数的节点才停下，这时候便得到了可能的终止节点。这些节点是可疑的函数节点
* 从调用节点的终点开始dfs（假设这个点是函数的起始节点）。只走上述的可疑节点
* 检查走过的所有节点，看是否能拼接为一个连续的地址（先对offset排序，然后前者的offset+length要等于后者的offset）
* 若能，则说明它们是同一个函数。将它们标记为一个函数。此时，push的返回地址不需要处理，因为对应的jump不会被执行。同时，放任这个没有入边的节点。因为它只包含了JUMPDEST；STOP，并不影响重定位

注意，存在selfdestruct的函数并非全部都会出现以上情况。如0x62e13095b0026b226538ae3e557507af875a6e31、0x8dc74d28b9821f7f9d0e95ab2d3c66f5276ac474就不会出现没有入边。

注意，这些包含selfdestruct函数，可能会出现类似递归的情况，即头结点存在于scc内，如0x1eeaf25f2ecbcaf204ecadc8db7b0db9da845327。

###### 4.27新坑

有些函数确实没有出边，并且返回的节点不是以jumpdest;stop的形式出现(0x385827aC8d1AC7B2960D4aBc303c843D9f87Bb0C)

```
function debit(address, bytes calldata) external returns (address, uint) { revert("not supported"); }
```

因为定义里面指明了返回的类型，因此编译器会专门用一些block来完成返回值的处理，但是实际上并不会走到这些block。

为了兼容之前的发现，这里将这种死字节码定义为：不是只有一条jumpdest的，没有入边的block

###### 4.28发现：没有入边的jumpdest

1. 在if里面调用mapping会导致没有入边的jumpdest出现。同时，这些jumpdest处的offset并不会被push

   ```
   pragma solidity ^0.4.0;
   
   contract test21 {
       mapping(address => uint256) balances;
   
       function test() returns (bool success) {
           if (balances[msg.sender] >= 0) {
               return true;
           } else {
               return false;
           }
       }
   }
   ```

2. 多层if嵌套，也会出现这种情况

   ```
   pragma solidity ^0.4.0;
   
   contract test22 {
       uint a;
       uint b;
       uint c;
   
       function test() returns (bool success) {
           if (a >= 0) {
               if(a > b){
                   return true;
               }
               else{
                   return false;
               }
           } else {
               if(c > b){
                   return true;
               }
               else{
                   return false;
               }
           }
       }
   }
   ```

3. if内包含函数，也会出现这种情况

   ```
   
   pragma solidity ^0.4.0;
   
   contract test23 {
   
       uint a;
       uint b;
   
       function judge(uint _a,uint _b)public returns(bool){
           return _a > _b;
       }
   
       function test() returns (bool success) {
           if (judge(a,b)) {
               return true;
           } else {
               return false;
           }
       }
   }
   ```

为了优化相关合约，这里确定寻找函数的一个新方法：

* 首先确定所有没有入边的节点
* 找到了函数的区间之后，用Dfs进行搜索
* 对搜到的所有节点进行排序
* 排序之后，看看是否满足：上一个节点的offset+上一个节点的长度==下一个节点的offset
* 如果不满足，则查看是否有没有入边的节点，可以填补这个空缺，有则继续检查。如果填不上，就是寻找失败



#### assert并非没有副作用

YECCToken里面，assert内调用了函数，会影响程序的状态。此时会找不到和目标程序状态相同的地址。这时候，应当拒绝优化该字节码

### 成功的用例

D:\Projects\iEvmOpt\contracts\0x208bbb6bcea22ef2011789331405347394ebaa51\optimized



### TODO

调整脚本，只输出合约的bin文件，或者删除不正确的bin文件

使用evmOpt，分析成功的合约，作为数据集的一部分



### 一些合约

##### 时间长但是evmopt可以算出的合约

ORACLEPSYCHOLIFE

##### ethersolve处理时间很长的合约

Exchange





597：jumpdest jump是tag34，应该跳到1650处，但是实际上没有跳

82:：jumpdest stop是tag9，因为调用了internal函数_fallback，tag9是 _fallback的返回地方



### 纠错

函数的入边可能只有一个，见KuaiWechatBusiness



### 新思路

#### 解决入边问题

因为ethersolve的问题，很多入边会找不齐，因此需要做一件事情，就是做一个边修复工作。

具体的方法为：

* 遍历所有的边关系，找到没有入边的点的集合

* 从起始节点，根据ethersolve的边关系，开始做dfs。做的是最普通的dfs，没有经过任何修改。同时，使用符号执行栈来记录跳转信息

* 如果在dfs中发现，存在一个块，它的末尾是Jump，而且栈顶元素对应一个没有入边的节点。那么说明，该跳转关系是缺失的，会为其添加一个跳转边

* 一切已经结束，这时做一个assertion check，查看是否所有非起始节点都有了入边。

  