import unittest
from web3 import Web3
from eth_tester import EthereumTester, PyEVMBackend
from vyper import compile_code
import pytest


def print_trace():
    import traceback
    # traceback.print_stack()

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
        # self.target.set_callback(self.caller.address, transact={})
        self.target.functions.set_callback(self.caller.address).transact()
        assert self.target.functions.callback().call() == self.caller.address

        print(f"Caller address: {self.caller.address}")

        # Test unprotected function.
        tx_hash = self.target.functions.unprotected_function("some value", True).transact()
        tx_receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
        logs = self.target.events.Message().processReceipt(tx_receipt)
        for log in logs:
            print(f"Event Message: {log['args']}")

        assert self.target.functions.special_value().call() == "surprise!"

        # Test protected function.
        self.target.functions.protected_function("some value", False).transact()
        assert self.target.functions.special_value().call() == "some value"

        self.target.functions.protected_function("a value", False).transact()
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
