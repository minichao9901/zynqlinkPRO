cmake_minimum_required(VERSION 3.15)
project(zynqdap_etm LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 11)
set(OPENCSD_BUILD_MIN_LIB_STATIC ON CACHE BOOL "" FORCE)
set(OPENCSD_FULL_PROJECT_LAYOUT OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
add_compile_options(-fexceptions)
add_subdirectory(../../third_party/OpenCSD-1.8.3 opencsd)
add_executable(zynqdap_etm decoder.cpp)
target_link_libraries(zynqdap_etm PRIVATE opencsd_c_api)
target_include_directories(zynqdap_etm PRIVATE ../../third_party/OpenCSD-1.8.3/decoder/include)
if(EMSCRIPTEN)
  set_target_properties(zynqdap_etm PROPERTIES OUTPUT_NAME opencsd SUFFIX .mjs)
  target_link_options(zynqdap_etm PRIVATE
    -O3 -fexceptions
    "-sMODULARIZE=1" "-sEXPORT_ES6=1" "-sENVIRONMENT=web,worker,node"
    "-sALLOW_MEMORY_GROWTH=1" "-sFORCE_FILESYSTEM=1"
    "-sEXPORTED_RUNTIME_METHODS=FS,callMain" "-sINVOKE_RUN=0" "-sEXIT_RUNTIME=0")
endif()
