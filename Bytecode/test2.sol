pragma solidity ^0.4.0;

contract test2{

    function g()private returns(uint){
        return h();
    }

    function h()private returns(uint){
		assert(1>2);
        return 0;
    }

    function f()public{
        g();
    }

}
