pragma solidity ^0.5.1;


contract owned {
    address public owner;
    constructor() public {
        owner = msg.sender;
    }
}



contract ethBank is owned{
    modifier onlyOwner {
        require(msg.sender == owner);
        _;
    }
    function moveBrickClear() onlyOwner public {
        require(msg.sender == owner, "only owner can use this method"); 
        selfdestruct(msg.sender);

    }
}