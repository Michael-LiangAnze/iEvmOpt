pragma solidity ^0.4.0;

//if嵌套导致jumpdest没有入边，而且不会被push
contract test22 {
    uint a;
    uint b;
    uint c;

    function test() returns (bool success) {
        if (a >= 0) {
            if(a > b){
                return true;
            }
            else{
                return false;
            }
        } else {
            if(c > b){
                return true;
            }
            else{
                return false;
            }
        }
    }
}
