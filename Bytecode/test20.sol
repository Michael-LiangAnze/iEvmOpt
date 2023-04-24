pragma solidity ^0.4.0;



contract test20{
    function safeAdd(uint _a,uint _b)public returns(uint) {
        uint sum = _a + _b;
        assert(sum >= _a && sum >= _b);
        return sum;
    }

    function initialize(bytes calldata /*data*/) external pure{
        revert("CANNOT_CALL_INITIALIZE");
    }
}