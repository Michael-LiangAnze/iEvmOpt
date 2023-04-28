
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
