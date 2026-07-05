


# async def abstract_role_info(state: CloneStoryboardState):
#     from app.services.llm import PRODUCER_QUERY_PROMPT, PRODUCER_SYSTEM_PROMPT, producer_model
#     log_node_start()
#     db=SessionLocal()
#     try:
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         clone_script.clone_progress = 36
#         clone_script.clone_status = CloneStatus.IMAGE
#         db.commit()
        
#         storyboard = state['storyboard_script']
#         storyboard_json = storyboard.model_dump()
#         query = PRODUCER_QUERY_PROMPT.format(
#             role_library=state['plot_role_library'],
#             storyboard=storyboard_json
#         )
#         messages = [SystemMessage(PRODUCER_SYSTEM_PROMPT),
#                     HumanMessage(query)]
#         response = await producer_model.ainvoke(
#             messages,
#             config={
#                 "configurable": {
#                     "temperature":0.7
#                 }
#             }
#         )
#         if not isinstance(response, CharacterManifest):
#             raise Exception("abstract_role_info llm输出格式错误")

#         logger.info(f'abstract_role_info output: {response.model_dump_json()}')

#         return Command(
#             update={'character_manifest': response},
#             goto='check_role_info'
#         )

#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('abstract_role_info 生成任务详情出错')
#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )
#         # return {'error': f'generate_storyboard failed. {str(e)}'}
#     finally:
#         db.close()

# async def check_role_info(state: CloneStoryboardState):
#     log_node_start()
#     try:
#         plot_role_name = [role['role_name'] for role in state['plot_role_library'] if 'role_name' in role]
#         character_manifest = state['character_manifest']
#         logger.info(f'plot_role_name:{plot_role_name}')


#         extra_role_messages = ''
#         for character in character_manifest.character_list:
#             if character.role_name not in plot_role_name:
#                 logger.info(f'find role_name:{character.role_name} not in plot_role_name')
#                 extra_role_messages += f'发现剧本中存在人物名({character.role_name}) 不在视频脚本中 \n'
        
#         retry_messages=''
#         if extra_role_messages:
#             retry_messages = '# 请重新对齐人物\n\n' + extra_role_messages
        
#         if retry_messages:
#             logger.info(f'extra_role_messages: {extra_role_messages}')
#         retry_cnt = state.get('retry_cnt', 0)
        
#         return {
#             'retry_messages': retry_messages,
#             'retry_cnt': retry_cnt + 1
#             }

#     except Exception as e:
#         error_message = f'check_storyboard_result failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('check_role_info 发生错误')
#         return {
#             'retry_messages':error_message,
#             'error': error_message,
#             'retry_cnt': settings.STORYBOARD_TRY_COUNT + 1
#         }
#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )

# async def need_retry_abstract(state: CloneStoryboardState):
#     retry_max = settings.STORYBOARD_TRY_COUNT
#     retry_cnt = state.get('retry_cnt', 0)
#     if state['retry_messages']:
#         if retry_cnt <= retry_max:
#             return 'abstract_role_info'
#         return 'process_error'
#     return 'initial_images'

# async def initial_images(state: CloneStoryboardState) -> Command[Literal['initial_videos', 'process_error']]:
#     """
#     生成图片
#     """
#     log_node_start()
#     db = SessionLocal()
#     try:
#         character_manifest = state['character_manifest']
#         if not isinstance(character_manifest, CharacterManifest):
#             raise Exception('character_manifest is None.')
        
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         gen_image = GenImage()

#         save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
#         make_dir(save_dir, re_create=False)

#         role_img_info = {}
#         for character in character_manifest.character_list:
#             if character.visual_anchor_prompt:
#                 params = GenImageParams(
#                     prompt=character.visual_anchor_prompt,
#                     image_size=ImageSize.SIZE_1024x1024.value
#                 )
#                 image_path_list = await gen_image.gen_image(gen_image_params=params, save_dir=save_dir, prefix=character.role_name)
#                 logger.info(f'get image path list: {image_path_list}')
#                 # if len(image_path_list) > 0:
#                 role_img_info[character.role_name] = image_path_list

#         # TODO: 增加生成每个分镜首帧的图片

#         clone_script.clone_status = CloneStatus.IMAGE_DONE
#         clone_script.clone_progress = 50
#         db.commit()
                    
#         return Command(goto='initial_videos')
#     except Exception as e:
#         error_message = f'initial_images failed. {str(e)}'
#         logger.exception('initial_images 发生错误')
#         logger.info(error_message)

#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )