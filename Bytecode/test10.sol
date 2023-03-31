pragma solidity ^0.4.0;

// 测试在部分冗余的函数体当中，出现完全冗余的情况

contract test10{
    uint a;
    uint c;
    bool b;

    function safeAdd(uint x,uint y)public returns(uint) {
        // 完全冗余
        if (b)
            c = 12;
        else
            c = 34;
        a = c + 2;
        assert(a > c && a >= 2);

        // 部分冗余
        uint z = x + y;
        assert(z >= x && z >= y);
        return z;
    }

    function f2()public{
        a = 0x40;
        a = safeAdd(a,0x35);
    }

}
