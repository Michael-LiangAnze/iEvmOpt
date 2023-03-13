pragma solidity ^0.4.0;

// 用于测试递归调用情况
contract test7 {


    function fibonacci(uint a) public returns(uint){
        assert(a > 0);
        if(a > 2)
            return fibonacci(a-1)+fibonacci(a-2);
        else
            return 0;
    }

    function f2() {
        uint res = fibonacci(10);
    }
}
