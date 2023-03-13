pragma solidity ^0.4.0;

contract test1{

    function sum(uint x)private returns(uint){
        assert(x > 0);
        uint j;
        uint sum = 0;
        for(j=0;j < x;++j)
            sum += j;
        return sum;
    }

    function f1()public{
        sum(10);
    }

}
