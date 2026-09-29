from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    city = State()            # маршрутная группа
    name = State()
    phone = State()
    address_city = State()    # конкретный город из группы
    street = State()
    house = State()
    apartment = State()
    pile = State()
    area_type = State()       # точная / примерная
    area = State()
    extras = State()
    pickup_date = State()
    confirm = State()


class RescheduleForm(StatesGroup):
    delivery_date = State()
