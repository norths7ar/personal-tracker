import streamlit as st
from datetime import date, timedelta
import pandas as pd

from core.db import init_db, get_diet_entries, update_diet_entry, delete_diet_entry, get_diet_summary

init_db()

st.title("📋 饮食查看")

# ── session state 初始化 ────────────────────────────────────────────────────
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None
if "delete_id" not in st.session_state:
    st.session_state.delete_id = None
if "flash" not in st.session_state:
    st.session_state.flash = None

# ── flash 消息 ──────────────────────────────────────────────────────────────
if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ── 筛选条件 ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    # 日期范围选择
    date_range = st.selectbox(
        "时间范围",
        ["今日", "最近7天", "最近30天", "本月", "上月", "全部", "自定义"],
        index=0
    )
    
with col2:
    # 餐顿类型筛选
    meal_type_filter = st.selectbox(
        "餐顿类型",
        ["全部", "早餐", "午餐", "晚餐", "零食", "其他"],
        index=0
    )
    
with col3:
    # 显示条数
    limit = st.number_input("显示条数", min_value=10, max_value=500, value=100, step=10)

# 自定义日期范围
custom_start = None
custom_end = None
if date_range == "自定义":
    col1, col2 = st.columns(2)
    with col1:
        custom_start = st.date_input("开始日期", value=date.today() - timedelta(days=7))
    with col2:
        custom_end = st.date_input("结束日期", value=date.today())

# 计算日期范围
today = date.today()
if date_range == "今日":
    start_date = today.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
elif date_range == "最近7天":
    start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
elif date_range == "最近30天":
    start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
elif date_range == "本月":
    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
elif date_range == "上月":
    first_day_this_month = today.replace(day=1)
    last_day_last_month = first_day_this_month - timedelta(days=1)
    start_date = last_day_last_month.replace(day=1).strftime("%Y-%m-%d")
    end_date = last_day_last_month.strftime("%Y-%m-%d")
elif date_range == "自定义":
    if custom_start and custom_end:
        start_date = custom_start.strftime("%Y-%m-%d")
        end_date = custom_end.strftime("%Y-%m-%d")
    else:
        # 如果自定义日期未选择，默认使用最近7天
        start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
else:  # 全部
    start_date = None
    end_date = None

# 获取数据
try:
    rows = get_diet_entries(
        start_date=start_date, 
        end_date=end_date, 
        meal_type=meal_type_filter if meal_type_filter != "全部" else None,
        limit=limit
    )
    
    if not rows:
        st.info("该时间段内没有饮食记录")
        st.stop()
    
    # 转换为DataFrame便于显示
    df = pd.DataFrame(rows)
    
    # 重命名列
    column_map = {
        "id": "ID",
        "date": "日期",
        "time": "时间",
        "meal_type": "餐顿",
        "food_name": "食物",
        "quantity": "份量",
        "description": "原始描述",
        "notes": "备注",
        "confidence": "置信度",
        "created_at": "创建时间"
    }
    
    df_display = df.rename(columns=column_map)
    
    # 选择要显示的列
    display_columns = ["日期", "时间", "餐顿", "食物", "份量", "备注"]
    df_display = df_display[display_columns]
    
    # 填充空值
    df_display = df_display.fillna("")
    
    # 显示数据
    st.subheader(f"饮食记录（共 {len(rows)} 条）")
    
    # 分页显示
    page_size = 20
    total_pages = max(1, (len(df_display) + page_size - 1) // page_size)
    
    page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, step=1)
    
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, len(df_display))
    
    st.dataframe(
        df_display.iloc[start_idx:end_idx],
        hide_index=True,
        use_container_width=True,
        column_config={
            "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD"),
            "时间": st.column_config.TextColumn("时间"),
            "餐顿": st.column_config.TextColumn("餐顿"),
            "食物": st.column_config.TextColumn("食物"),
            "份量": st.column_config.TextColumn("份量"),
            "备注": st.column_config.TextColumn("备注"),
        }
    )
    
    st.caption(f"显示第 {start_idx+1}-{end_idx} 条，共 {len(df_display)} 条")
    
    # 编辑/删除功能
    st.divider()
    st.subheader("记录操作")
    
    col1, col2 = st.columns(2)
    with col1:
        edit_id = st.number_input("要编辑的记录ID", min_value=1, value=1, step=1)
        if st.button("编辑记录", type="secondary", use_container_width=True):
            st.session_state.edit_id = edit_id
            st.rerun()
    
    with col2:
        delete_id = st.number_input("要删除的记录ID", min_value=1, value=1, step=1)
        if st.button("删除记录", type="secondary", use_container_width=True):
            st.session_state.delete_id = delete_id
            st.rerun()
    
    # 编辑界面
    if st.session_state.edit_id:
        edit_id = st.session_state.edit_id
        record_to_edit = next((r for r in rows if r["id"] == edit_id), None)
        
        if record_to_edit:
            st.divider()
            st.subheader(f"编辑记录 ID: {edit_id}")
            
            with st.form("edit_form"):
                col1, col2 = st.columns(2)
                with col1:
                    edit_date = st.date_input("日期", value=date.fromisoformat(record_to_edit["date"]))
                with col2:
                    edit_time = st.text_input("时间", value=record_to_edit.get("time", ""))
                
                edit_meal_type = st.selectbox(
                    "餐顿类型",
                    ["早餐", "午餐", "晚餐", "零食", "其他"],
                    index=["早餐", "午餐", "晚餐", "零食", "其他"].index(record_to_edit.get("meal_type", "其他")) 
                    if record_to_edit.get("meal_type") in ["早餐", "午餐", "晚餐", "零食", "其他"] else 4
                )
                
                edit_food_name = st.text_input("食物名称", value=record_to_edit.get("food_name", ""))
                edit_quantity = st.text_input("份量", value=record_to_edit.get("quantity", ""))
                edit_description = st.text_area("原始描述", value=record_to_edit.get("description", ""), height=80)
                edit_notes = st.text_area("备注", value=record_to_edit.get("notes", ""), height=60)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("保存修改", type="primary", use_container_width=True):
                        update_diet_entry(
                            edit_id,
                            date=edit_date.strftime("%Y-%m-%d"),
                            time=edit_time or None,
                            meal_type=edit_meal_type,
                            food_name=edit_food_name,
                            quantity=edit_quantity,
                            description=edit_description,
                            notes=edit_notes or None
                        )
                        st.session_state.edit_id = None
                        st.session_state.flash = f"✅ 记录 ID {edit_id} 已更新"
                        st.rerun()
                
                with col2:
                    if st.form_submit_button("取消", use_container_width=True):
                        st.session_state.edit_id = None
                        st.rerun()
        else:
            st.warning(f"未找到 ID 为 {edit_id} 的记录")
            if st.button("关闭编辑"):
                st.session_state.edit_id = None
                st.rerun()
    
    # 删除确认界面
    if st.session_state.delete_id:
        delete_id = st.session_state.delete_id
        record_to_delete = next((r for r in rows if r["id"] == delete_id), None)
        
        if record_to_delete:
            st.divider()
            st.subheader(f"确认删除记录 ID: {delete_id}")
            
            st.warning("⚠️ 以下记录将被永久删除：")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("日期", record_to_delete["date"])
            with col2:
                st.metric("餐顿", record_to_delete.get("meal_type", "未知"))
            with col3:
                st.metric("食物", record_to_delete.get("food_name", "未知"))
            
            st.caption(f"原始描述：{record_to_delete['description']}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("确认删除", type="primary", use_container_width=True):
                    delete_diet_entry(delete_id)
                    st.session_state.delete_id = None
                    st.session_state.flash = f"✅ 记录 ID {delete_id} 已删除"
                    st.rerun()
            
            with col2:
                if st.button("取消", use_container_width=True):
                    st.session_state.delete_id = None
                    st.rerun()
        else:
            st.warning(f"未找到 ID 为 {delete_id} 的记录")
            if st.button("关闭"):
                st.session_state.delete_id = None
                st.rerun()
    
    # 侧边栏：统计信息
    with st.sidebar:
        st.subheader("📊 统计摘要")
        
        if start_date and end_date:
            try:
                summary = get_diet_summary(start_date, end_date)
                
                if summary["meal_stats"]:
                    st.caption(f"时间段：{start_date} 至 {end_date}")
                    
                    # 餐顿类型分布
                    st.write("**餐顿类型分布**")
                    for stat in summary["meal_stats"]:
                        st.progress(stat["count"] / max(1, len(rows)), 
                                  text=f"{stat['meal_type']}: {stat['count']} 次")
                    
                    # 最近记录预览
                    st.write("**最近记录**")
                    for i, rec in enumerate(summary["recent"][:5], 1):
                        st.caption(f"{i}. {rec['date']} {rec['meal_type']}: {rec['food_name']} {rec.get('quantity', '')}")
            except Exception as e:
                st.caption(f"统计加载失败：{e}")
        
        # 导出功能
        st.divider()
        st.subheader("导出数据")
        
        if st.button("导出为CSV", use_container_width=True):
            csv = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="下载CSV文件",
                data=csv,
                file_name=f"饮食记录_{today.strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )

except Exception as e:
    st.error(f"加载数据时出错：{e}")
    st.exception(e)