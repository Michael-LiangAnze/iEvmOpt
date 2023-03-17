pragma solidity ^0.4.0;

contract assertExample{
    uint a;
    uint b;

    function safeAdd(uint _a,uint _b)returns(uint){
        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        return sum;
    }

    function f1()public{
        a = safeAdd(a,0x15);
        a = 0x40;
        a = safeAdd(a,0x35);
    }

}
