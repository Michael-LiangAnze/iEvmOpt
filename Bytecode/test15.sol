pragma solidity ^0.4.0;

// constructor中触发codecopy，函数体中存在部分冗余和完全冗余，以及codecopy
contract test15 {
    string name;

    constructor() public {
        name = "init name:asdaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    }

    function setName(string _name) public {
        name = _name;
    }

    function f() public {
        setName(
            "0x1324654684486544656654204464465489498635156546498618555849651238974561849561986531246354125454545463351aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        );
    }

    uint256 a;
    uint256 c;

    function f1(bool b) public {
        if (b) c = 12;
        else c = 34;
        a = c + 2;
        assert(a >= c && a >= 2);
    }

    function safeAdd(uint256 x, uint256 y) public returns (uint256) {
        uint256 z = x + y;
        assert(z >= x && z >= y);
        return z;
    }

    function f2() public {
        a = safeAdd(a, 0x15);
        a = 0x40;
        a = safeAdd(a, 0x35);
    }
}
