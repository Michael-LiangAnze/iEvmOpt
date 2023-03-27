pragma solidity ^0.4.0;

// 对一个block，“掐头去尾”的情况
contract test9{
    uint a;
    uint b;

    function safeAdd(uint _a,uint _b)private returns(uint) {
        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        uint sum1 = _a + _b;
        assert(sum1 >= _a && sum1 >= _b);
        return sum1;
    }

    function f1()public{
        a = 0x40;
        a = safeAdd(a,0x35);
    }

}
