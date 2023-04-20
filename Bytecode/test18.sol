pragma solidity ^0.4.0;

// 使用函数作为函数参数
contract test18{
    uint a;
    uint b;
    bool isCheck;

    function safeAdd(bool isCheck)public returns(uint) {
        uint sum = a + b;
        if (isCheck)
            assert(sum >= a && sum >= b);
        return sum;
    }

    function getIsCheck() public returns(bool) {
        return isCheck;
    }

    function getRes()public returns(uint) {
        return safeAdd(getIsCheck());
    }

    function setNum(uint _a,uint _b) public{
        a = _a;
        b = _b;
    }

}
