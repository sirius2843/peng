"""Explicit per-draft author judgments and observed tool signals; never infer from intent."""
import datetime as dt
from providers import TZ,now

def normalize(data,cutoff):
    result=[]
    judgment=str(data.get('author_view','')).strip()
    signal=str(data.get('tool_signals','')).strip()
    if len(judgment)>4000 or len(signal)>4000:raise ValueError('本人观点或工具信号过长，请精简')
    if (judgment or signal) and data.get('author_confirmed') is not True:
        raise ValueError('请勾选确认：这些观点和信号由本人提供')
    horizon=data.get('author_horizon','short')
    if horizon not in {'short','medium_long'}:raise ValueError('请选择观点期限')
    for i,text in enumerate(filter(None,(x.strip() for x in judgment.splitlines())),1):
        result.append({'id':f'AUTHOR-J{i}','kind':'author_judgment','text':text,'horizon':horizon,
                       'source':'本人当次明确确认','status':'author_confirmed','observed_at':cutoff.isoformat(),
                       'available_at':cutoff.isoformat(),'submitted_at':now().isoformat(),
                       'verification_scope':'本人对本稿时点的观点，不代表客观事实已核验'})
    if signal:
        try:
            when=dt.datetime.fromisoformat(str(data.get('signal_time','')).replace('Z','+00:00'))
            if when.tzinfo is None:when=when.replace(tzinfo=TZ)
            if when>cutoff:raise ValueError('工具信号晚于本稿资料截点，请调整信号时间或改用其他栏目')
        except (TypeError,ValueError) as exc:
            raise ValueError(str(exc) if '晚于' in str(exc) else '请填写真实工具信号的观测时间（北京时间）') from None
        for i,text in enumerate(filter(None,(x.strip() for x in signal.splitlines())),1):
            result.append({'id':f'AUTHOR-T{i}','kind':'tool','text':text,'source':'本人提供的真实工具记录',
                           'status':'author_confirmed','observed_at':when.isoformat(),'available_at':when.isoformat(),
                           'submitted_at':now().isoformat(),'verification_scope':'本人录入，未独立重算；只能引用所提供的信号'})
    return result
