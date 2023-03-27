# iEvmOpt

[TOC]

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

###### 6.因为程序编写而出现的解析问题

原来的想法：将冗余类型分为完全冗余、部分冗余和不冗余；根据每个invalid的各条路径的情况进行判断。

但是实际上，不冗余类型是会判断错误的，如test8：

```
pragma solidity ^0.4.0;

// 不冗余的例子
contract test8{
    uint a;
    uint b;

    function safeAdd(uint _a,uint _b)returns(uint){
        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        return sum;
    }
}
```



<img src="D:\Projects\iEvmOpt\pics\test8_cfg.png" style="zoom:50%;" />

先给出各条边的约束情况:

* 140->163：sum < a的情况。如果为真则163会跳到invalid
* 140->158：sum >= a
* 158->163:  sum  >= b的情况。如果为真则163会跳到invalid

显然，一旦走了140->158的边，则结果一定为不溢出。但是却将该路径判断为不可达，从而不能得到不冗余的类型。

因此，舍弃类型“不冗余”。

### 约束收集与求解

#### 路径分类

#### 约束求解

给定一个假设：所有的invalid节点都是通过jumpi跳转进入的。因此只需要收集每次jumpi的condition，并加入求解器即可。



### 完全冗余的优化

#### 基本假设

* 要进入invalid节点，必然通过jumpi。其中jumpi判断false则跳转到invalid，判断true则跳转到invalid的下一个地址。
* dispatcher中的内容不能被修改。

#### 基本思路

完全冗余的优化过程大致如下：

1. 生成支配树
2. 取出一个invalid节点，取出其中一条函数调用链，随意指定其中一条路径，开始做符号执行，并记录路径上各个地址的程序状态
3. 在支配树中，从invalid节点开始向根出发，找到程序状态相同的最远的地址，这个地址到invalid节点之间的序列便是assertion相关的序列
4. 直接在assertion相关的序列位置插入jump，目的地为invalid的地址+1。



#### 修改字节码

将原字节码的内容读入，然后进行匹配，找到原函数体的起始位置，后面根据偏移量直接填入内容即可。



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

解释一下为什么需要试填入：新地址的字节数可能和原地址不一样，如果新地址更小，则可以缩短push的地址，减少block的字节数；如果新地址更长，则需要在原来的地方多push一些字节，增加block的字节数。

试填入阶段，一旦字节数发生了变化，则整个过程都需要重新进行计算。



