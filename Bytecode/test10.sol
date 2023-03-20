
pragma solidity ^0.4.0;
contract test10{
    uint a;
    uint c;

    function f1(bool b)public{
        if (b)
            c = 12;
        else
            c = 34;
        a = c + 2;
        assert(a > c && a >= 2);
    }
    function safeAdd(uint x,uint y)public returns(uint) {
        uint z = x + y;
        assert(z >= x && z >= y);
        return z;
    }

    function f2()public{
        a = safeAdd(a,0x15);
        a = 0x40;
        a = safeAdd(a,0x35);
    }

}
