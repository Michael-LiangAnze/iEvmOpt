pragma solidity ^0.4.0;

contract test2{

    function g()private returns(uint){
        return 1;
    }


    function f()public returns(uint){
        uint i = 0;
        uint sum = 0;
        for (;i < 5;i+=1)
            sum += g();
            assert(i >= 0);
    }

}
