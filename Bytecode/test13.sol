pragma solidity ^0.4.0;

// 触发codecopy，而且存在完全冗余和部分冗余
contract test13{
    string name;
    uint256 a;
    uint256 c;

    function f1(bool b) public {
        if (b)
            c = 12;
        else
            c = 34;
        a = c + 2;
        assert(a >= c && a >=2);
    }

    function safeAdd(uint x, uint y) public returns (uint) {
        uint z = x + y;
        assert(z >= x && z >= y);
        return z;
    }

    function f2() public{
        a = safeAdd(a,0x15);
        a = 0x40;
        a = safeAdd(a,0x35);
    }

    function setName(string _name)public{
        name = _name;
    }

    function f()public{
        setName("0x1324654684486544656654204464465489498635156546498618555849651238974561849561986531246354125454545463351aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    }
}
