from __future__ import annotations

from typing import Any

MESSAGES_COLLECTION = "im_messages"


def fetch_message_window(
    store,
    base_query: dict[str, Any],
    *,
    limit: int | None = None,
    before_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """聊天记录懒加载：直接在数据库层只取窗口数据，不全量加载。

    返回 (items, has_more)，items 按 created_at 升序：
    - before_id 为空：取最新的 `limit` 条（首屏）。
    - before_id 给定：以该消息为游标，取它之前（created_at 更小）最新的 `limit` 条（上滑加载更早）。
      游标消息不存在（如已删除）时返回 ([], False)，让前端安全停止。
    - has_more 表示窗口之上是否还有更早的消息；用 limit+1 多取一条来判定，省掉额外的 count 查询。
    - limit 为空/<=0：不分页，按升序返回符合条件的全部（保留给可能的内部全量调用）。

    `base_query` 给出窗口的固定过滤条件（单聊用 conversation_id，群聊用 room_id[+conversation_id]），
    游标范围条件 created_at<cursor 由本函数追加，下推到数据库执行。
    """
    base_query = dict(base_query)

    if before_id:
        cursor = store.find_one(MESSAGES_COLLECTION, {**base_query, "message_id": before_id})
        if cursor is None:
            return [], False
        query = {**base_query, "created_at": {"$lt": cursor.get("created_at", 0)}}
    else:
        query = base_query

    if not limit or limit <= 0:
        return store.find_many(MESSAGES_COLLECTION, query, sort=[("created_at", 1)]), False

    # 倒序多取一条：拿到则说明窗口之上还有更早记录（has_more），随后裁掉并翻回升序。
    fetched = store.find_many(MESSAGES_COLLECTION, query, sort=[("created_at", -1)], limit=limit + 1)
    has_more = len(fetched) > limit
    window = fetched[:limit]
    window.reverse()
    return window, has_more
