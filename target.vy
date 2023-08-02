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
