pragma solidity ^0.4.0;

// 尝试触发codecopy指令
contract test12{
    string name;

    function setName()public{
        name = "0x1324654684486544656654204464465489498635156546498618555849651238974561849561986531246354125454545463351";
    }

    function getName()public returns(string){
        return name;
    }

}
