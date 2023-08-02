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
