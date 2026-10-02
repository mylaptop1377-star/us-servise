from aiogram.fsm.state import State, StatesGroup


class PurchaseStates(StatesGroup):
    waiting_player_id = State()
    confirming_player = State()
    choosing_package = State()
    waiting_receipt = State()


class AdminStates(StatesGroup):
    adding_package_name = State()
    adding_package_uc = State()
    adding_package_price = State()
    choosing_package_to_edit = State()
    choosing_package_field = State()
    editing_package_value = State()
    setting_card = State()
    setting_holder = State()
    rejecting_order = State()
    broadcasting = State()
