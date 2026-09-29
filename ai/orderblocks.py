"""Order-block facade."""
from smart_money.order_blocks import detect_order_blocks, update_order_block

update_order_block_state = update_order_block
__all__ = ["detect_order_blocks", "update_order_block", "update_order_block_state"]
