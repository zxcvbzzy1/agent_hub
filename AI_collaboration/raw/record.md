[LLM_infra.py](agent_flow/infra/LLM/LLM_infra.py) 帮我写一个继承于LLM_Client的一个新的客户端类，这个客户端类是一个统一的适配层，用来调用本地的CLI agent，如codex，Claude code这类本地的cli应用，将用户的问题转发给他，并将他的问答或者输出内容转回去

[LLM_infra.py](agent_flow/infra/LLM/LLM_infra.py) [agent_flow](agent_flow/) [web_front](web_front/) 我想开发一个平台，类似IM聊天交互，每个agent有自己的名称图像，可以1v1与单个agent对话，也可以用拉群聊的方式，一个群聊包含多个agent，可以@agent指定任务，也可以由PlanOrchestrator进行编排，这个平台可以把Claude code ，codex等当作agent，例如可以对这个agent说，请用Claude code写一个React组件，完成这样的任务，且消息类型支持文本，代码块，图片，文件，网页预览卡片，diff视图卡片，部署卡片等，以及预留消息操作的接口（回复，引用，复制，展开，应用diff等），该怎么设计接入Claude code ，codex呢，可以复用现在已经写好的agent_flow部分，也可以采用类似DDD架构，新创一个文件夹，写相应的补充逻辑，调用agent_flow里的代码等，如果改动内容过多，可以新建后端文件夹开微服务，前端也是可以在web_front改动，也可以在新的IM_front里写用ant design vue+axios+pinia+vue router，参照web_front的现代美观页面。项目的python环境为/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin
mongodb环境为/Users/zxcvbzzy1/Desktop/database/mongodb/mongodb-macos-aarch64--8.3.2/bin
可以创新的数据库

[IM_front](IM_front/)IM im_backend后端可以直接用agent_flow里domain,infra层里的东西，同时IM_front里的页面设计过于死板，请加一个登入注册界面，以及更加美观现代一点，有layout。在chat页面，左边应该是各个agent列表以及已经创建的agent群的群名有群头像，agent头像显示，选择对应的agent后，左边则变为对应agent的消息列表，如果是群的话则是群里的编排任务列表，中间是聊天页面主体，其中@功能不是单独拿出来的，而是在群的聊天页面里对话框输入@时可以显示群内的agent列表，右边栏去掉，替换为一个悬浮按钮，可以展示出上传过的文件，agent信息之类，如果是群对话则展示群内agent

[ChatView.vue](IM_front/src/views/ChatView.vue) 目前前端的页面配色有点死板，配色布局变得更加灵动现代点，可以用渐变色等，同时ChatView.vue里的悬浮信息 Drawer不由悬浮按钮触发，可由聊天页面里上面的chat-main的header点击触发

[ChatView.vue](IM_front/src/views/ChatView.vue) [providers.py](agent_flow/domain/context/providers.py) [IM_front](IM_front/) 目前逻辑有点问题，与单个agent对话，不需要编排与run等逻辑，就是单个agent多轮对话就行，然后ChatView.vue左下侧的消息列表里不是显示消息，是对话/会话,每个对话里注入的是当前对话消息历史即为providers.py里的HistoryProvider。并且目前agent群聊没有正常显现出来，群聊里才涉及编排等逻辑，并且执行者就是agent群的群成员agent，每个群默认带有plan agent和编排器。IM_front domain可以多几个模块，而不是统一为models.py

[ChatView.vue](IM_front/src/views/ChatView.vue)  [conversations.py](im_backend/api/routes/conversations.py)  [router.py](agent_flow/api/runs/router.py) [events](agent_flow/application/events/)  [ChatView.vue](web_front/src/views/chat/ChatView.vue)  [runtime_hooks.py](agent_flow/domain/runtime_hooks.py) 模仿agent_flow/api/runs/router.py里/{run_id}/events路由，在im_backend/api/里也返回SSE事件流，其中im_backend/api/routes/conversations.py里/conversations/{conversation_id}/stream如果没有用到可以删掉，返回的事件流可以参考agent_flow/application/services/events.py里的。前端监听这些事件，并在im_front里 ChatView.vue里的对话里要展现，展现的方式可以跟web_front里ChatView.vue类似。但im_front里，单聊里可以展示模型的think工具调用等内容，群聊里，则是各个模型的运行内容think，工具调用等由各个模型发出内容等.agent_flow里自身事件总线暴露的钩子为runtime_hooks.py

[ChatView.vue](IM_front/src/views/ChatView.vue)  [ChatView.vue](web_front/src/views/chat/ChatView.vue)  [services.py](im_backend/application/services.py) 把im_front前端页面里的runtimeEventNames，SSE事件放在另一个文件里。同时增加agent群解散，删除agent，删除对话等，删除agent，agent群后，相应的对话历史事件也要同步删除。增加创建agent的选项，并且agent群里对话页面下，composer-actions里有plan agent的选择，把他放到群抽屉里面，像PlanOrchestratortrator一样列出，可以更换.
创建新的agent的逻辑类似于web_front里。后端的services.py可以拆为多个文件


❯ workflow 目前有几个任务需要改善，首先是 @IM_front/src/views/ChatView.vue 里，agent回复的消息宽度可以不受限制，宽一点，然后是左边的边栏可以展开与收缩， @IM_front/src/components/ArtifactCard.vue里diff工件，未更改的部分可以收齐；其次是增加消息类型的操作，如回复，引用，重新生成，展开预览（可以是点击后旁边增加一个大块的预览界面），收藏等，收藏是把关键信息作为该次对话，群聊里面的长期上下文（固定写入）-（这个可以参考@agent_flow/domain/context/providers.py 等相关设置，可以直接在里面添加新的provider ）,同时边栏上的会话列表，支持置顶归档搜索等操作，归档类似于收藏，但是会话级别，目前只留相关接口即可，后续再增加milvus向量数据库RAG等会话搜索。最后agent创建时，可以上传自定义的agent头像，以及相应工具的选择 这块可以复用@agent_flow/application/services/contexts.py 逻辑，选择不同的AvailableToolsProvider即可。如果有需要确定的设计边界向我确认，如果我更好的设计向我确认。一些简单的任务可以用默认的简单模型如sonnet4.6，复杂的和最后收敛汇总的，用opus4.8,具体由你自行分配

workflow @IM_front/src/views/ChatView.vue 目前有几个问题需要修改，一个是收藏到固定上下文的UI界面，支持点一下是收藏，再点一下取消收藏，同时图标的颜色有所变化；一个是边栏agent上加上能力标签，其中便签由创建agent时自行输入，也可以由对话式创建里，自动创建，大约1～2个；还有一个是chat-hero里点击展开的抽屉里展示上下文信息里，里面展示的不再是“该 Agent 的对话”而是此事对话收藏的消息；还有一个是， @im_backend/application/services/_shared/inline_artifacts.py 和对应的前端页面ChatView.vue 里artifacts支持下载（文档，网页文件等），其中群聊里最后汇总的artifacts是支持打包下载，可以给消息操作里加上下载操作。如果有需要确定的设计边界向我确认，如果我更好的设计向我确认。一些简单的任务可以用默认的简单模型如sonnet4.6，复杂的和最后收敛汇总的，用opus4.8,具体由你自行分配


 workflow 目前有几个bug，一个是 @agent_flow/infra/tool/builtin/system.py 这个里bash执行命令没问题，但有时模型输出的格式arguments.command但里面嵌套了一大段 Shell + Markdown + JSON 示例代码，导致外层的JSON解析失效。所以我打算加个文件操作工具，有File Tools:- read_file- write_file- append_file- edit_file- apply_patch- list_dir- glob- search_text这些命令，然后bash走这些命令不能覆盖的操作，模仿原来文件添加新的工具。另外一个是   @im_backend/application/services/_shared/inline_artifacts.py @IM_front/src/views/ChatView.vue 里deploy不支持下载，添加deploy artifacts下载操作，可以添加一个新的属性，里面放下载的目录，点击下载后，将这个目录下的文件打包为一个整体下下来，这个目录应该在工作目录下，不然被拒 绝。还有一个是deploy artifact的每次点击页面默认是运行中，就算关闭，刷新一下后还是运行中，但后端确实关了，这应该是前端显示问题修复一 未读红点：由于后端没有全局推送流（SSE 只覆盖当前打开的房间/会话），要让你离开某会话后它仍能实时冒红点并显示数量，需要选一种统计方案。你倾向哪种 


workflow 目前有几个需要优化的地方，一个是 @IM_front/src/views/ChatView.vue @im_backend/application/services/_shared/inline_artifacts.py @IM_front/src/components/ArtifactCard.vue  里 deploy artifact的消息要支持部署的消息操作，就是添加部署按钮，点击后可以一键部署；还有一个是 @agent_flow/infra/tool/builtin/file_tools.py 里的几个工具可以合成一个，各个工具为这个大工具的一个属性，跟 @agent_flow/infra/tool/builtin/artifacts.py 一样  ；一个是 @agent_flow/domain/context/providers.py 里添加skill的供应商，用于将skill注入到上下文里，同时在 @agent_flow/domain/ 里添加skill文件夹用于放skill管理的相关逻辑，如Skill Registry + Retriever 等，skill不是固定Prompt应该是记忆存储，可以被检索召回注入。这个召回分两层。一个是系统检索召回，一个是做成工具可以让智能体调用召回。召回 可以写个简单的向量匹配，做成模块，便于后续替换为RAG。系统检索召回一般发生在用户prompt注入后，如 @agent_flow/domain/agent_base.py 里start()里 self.prepare_start(prompt, keep_history=True)后可以紧接着skill召回。如果有需要确定的设计边界向我确认，如果我更好的设计向我确认。一些简单的任务可以用默认的简单模型如sonnet4.6，复杂的和最后收敛汇总的，用opus4.8,具体由你自行分配 

workflow @agent_flow/infra/tool/builtin/diff_editor.py
这个目前是把编辑文档保存的功能作为open_document供agent自行调用，但我是想把这个编辑文档保存的功能 @IM_front/src/views/ChatView.vue在这个页面里的消息操作里实现，点击消息操作编辑后编辑文档，然后保存就可以改原本的文件。@IM_front/src/components/ArtifactCard.vue
然后有个小bug当我回退后创建一个新的历史版本，可是显示的还是之前的版本。然后增加一个工具展示的页面，模仿@IM_front/src/views/SkillsView.vue的样子，但不必新建删除修改内容等，只是纯展示，但可以进行一些参数配置，如下一点所讲的。最后有个想优化的地方， @agent_flow/infra/tool/builtin/system.py里目前对于危险命令是直接拒绝执行，我想把逻辑改为向人工确认，这块人工确认的流程我已经写好在 @agent_flow/infra/tool/common_func.py里，你看可不可以复用。原来直接拒绝的逻辑不要删，把他改为参数配置。如果有需要确定的设计边界向我确认，如果我更好的设计向我确认。一些简单的任务可以用默认的简单模型如sonnet4.6，复杂的和最后收敛汇总的，用opus4.8,具体由你自行分配。



帮我创建一个写前端的智能体，名字，标签，系统提示词等，你自行决定，工作目录为/Users/zxcvbzzy1/Desktop/byte_dance_test

@执行者1 生成一个只包含注册登入的web的设计文档，包含api路由参数，用sqlite数据库，即api文档，保存并返回路径 @前端编码助手 根据生成的文档，设计web UI界面，保存展示部署并返回路径，@FastAPI 后端助手 根据@执行者1 @前端编码助手 生成的文档和前端代码，生成fastapi后端，后端环境python为/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin，用sqlite数据库,展示保存返回并部署，返回路径

md渲染；创建新的工具，这个工具用来与用户协同修改某个文件，每次创建该文件的Diff、展示该文件的版本历史，这个工具同样发生artifact.事件，artifact上消息操作支持一键应用生成的Diff，局部修改（选中代码 -> 在聊天中描述修改意见）。优化，并发，消息点，消息流中事件加载，消息加载，群聊的智能体备份，工具人工确认


[requirements.md](ship_file/requirements.md) 这是项目需求， @agent_flow 这里是智能体核心的代码， @im_backend/ 这是网页后端的代码， @IM_front/ 这是网页前端的代码，请你根据项目需求， 参照[PRD_skill.md](ship_file/PRD_skill.md) 文档专家工作手册里的要求，和具体实现的代码，完成产品设计文档的撰写。注意不要更改代码这三个文件夹里的任何东西。只用写产品设计文档即可

[07-功能需求.md](ship_file/PRD/AgentHub/07-功能需求.md) 这个功能需求有优化的地方，不能这么分，可以按 [requirements.md](ship_file/requirements.md) 核心功能下的点来分，第一点也可以拆分。然后每个功能对应一张业务流程图，用泳道图来画。每个功能点下的分点还是和原来一致

