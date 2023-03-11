pragma solidity ^0.4.0;

contract test2{

    function g(uint x)private returns(uint){
        return h(x - 1);
    }

    function h(uint x)private returns(uint){
		assert(x > 0);
        if (x > 10)
            return f(x - 1);
        else 
            return 0;
    }

    function f(uint x)public returns(uint){
        return g(x - 1);
    }

}
