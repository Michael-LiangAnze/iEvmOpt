pragma solidity ^0.4.0;

// test15中的字符串的缩短版
contract test16 {
    string name;

    constructor() public {
        name = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    }

    function setName(string _name) public {
        name = _name;
    }

    function f() public {
        setName(
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
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
