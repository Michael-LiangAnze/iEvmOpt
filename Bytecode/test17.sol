pragma solidity ^0.4.0;

// 部分冗余的例子，但是冗余的函数中出现了连通分量
contract test17{
    uint a;
    uint b;

    function safeAdd(uint _a,uint _b)public returns(uint) {
        uint i = 0;
        uint temp = 0;
        for (;i < 5;i+=1)
            temp += i;

        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        return sum;
    }

    function f()public{
        a = safeAdd(a,0x15);
        a = 0x40;
        a = safeAdd(a,0x35);
    }

}
