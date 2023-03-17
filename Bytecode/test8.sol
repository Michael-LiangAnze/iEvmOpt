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