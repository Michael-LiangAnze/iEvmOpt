pragma solidity ^0.4.0;


//if调用mapping导致jumpdest没有入边，而且不会被push
contract test21{
    mapping(address=>uint256) balances;


    function transfer(address _to, uint256 _value) returns (bool success) {
        if (balances[msg.sender] >= _value && _value > 0) {

            balances[msg.sender] -= _value;

            balances[_to] += _value;

            return true;

        } else { return false; }

    }
}