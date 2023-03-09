pragma solidity ^0.4.0;

contract test{

    function sum(uint x)private returns(uint){
        uint j;
        uint sum;
        sum = 0;
        for(j=0;j < x;++j)
            sum += j;
        return sum;
    }

    function f1()public{
        sum(10);
    }

}
