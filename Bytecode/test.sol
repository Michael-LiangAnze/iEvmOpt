pragma solidity ^0.4.0;

contract assertExample{

    function Abs(uint x)returns(uint){
        if(x > 0)
            return x;
        else 
            return -x;
    }

    function f1()public{
        Abs(1);
    }

}
