pragma solidity ^0.4.0;

contract assertExample1{
    function safeAdd(uint _a,uint _b)returns(uint){
        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        return sum;
    }
}
