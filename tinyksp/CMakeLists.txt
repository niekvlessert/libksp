cmake_minimum_required(VERSION 3.18)
project(tinyksp_standalone VERSION 1.9.9 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)


# libvgm YMF278B wave/PCM backend. TinyKSP retains its own OPL3/FM backend.
include(FetchContent)
set(BUILD_LIBAUDIO OFF CACHE BOOL "" FORCE)
set(BUILD_LIBEMU ON CACHE BOOL "" FORCE)
set(BUILD_LIBPLAYER OFF CACHE BOOL "" FORCE)
set(BUILD_PLAYER OFF CACHE BOOL "" FORCE)
set(BUILD_VGM2WAV OFF CACHE BOOL "" FORCE)
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(USE_SANITIZERS OFF CACHE BOOL "" FORCE)
set(LIBRARY_TYPE STATIC CACHE STRING "" FORCE)
set(SNDEMU__ALL OFF CACHE BOOL "" FORCE)
set(SNDEMU_YMF278B_ALL ON CACHE BOOL "" FORCE)
set(SNDEMU_YM2413_EMU ON CACHE BOOL "" FORCE)
set(SNDEMU_AY8910_EMU ON CACHE BOOL "" FORCE)
set(SNDEMU_YMF262_ALL OFF CACHE BOOL "" FORCE)
set(SNDEMU_YMF262_MAME OFF CACHE BOOL "" FORCE)
set(SNDEMU_YMF262_ADLIBEMU OFF CACHE BOOL "" FORCE)
set(SNDEMU_YMF262_NUKED OFF CACHE BOOL "" FORCE)
set(TINYKSP_LIBVGM_SOURCE_DIR "" CACHE PATH "Use an existing libvgm checkout instead of downloading it")
set(TINYKSP_LIBVGM_GIT_TAG master CACHE STRING "libvgm revision used by FetchContent")

set(TINYKSP_LIBKSS_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/libkss" CACHE PATH
    "Use an existing libkss checkout")
if(NOT EXISTS "${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2149/emu2149.c")
    message(FATAL_ERROR
        "TinyKSP requires the libkss submodule. Initialize it with git submodule update --init --recursive, "
        "or set TINYKSP_LIBKSS_SOURCE_DIR to a libkss checkout.")
endif()

if(TINYKSP_LIBVGM_SOURCE_DIR)
    set(_tinyksp_libvgm_checkout "${TINYKSP_LIBVGM_SOURCE_DIR}")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/libvgm-master/CMakeLists.txt")
    message(STATUS "Using bundled libvgm checkout: ${CMAKE_CURRENT_SOURCE_DIR}/libvgm-master")
    set(_tinyksp_libvgm_checkout "${CMAKE_CURRENT_SOURCE_DIR}/libvgm-master")
else()
    FetchContent_Declare(libvgm
        GIT_REPOSITORY https://github.com/ValleyBell/libvgm.git
        GIT_TAG ${TINYKSP_LIBVGM_GIT_TAG}
        GIT_SHALLOW TRUE
    )
    FetchContent_GetProperties(libvgm)
    if(NOT libvgm_POPULATED)
        FetchContent_Populate(libvgm)
    endif()
    set(_tinyksp_libvgm_checkout "${libvgm_SOURCE_DIR}")
endif()

# Build a private copy so the TinyKSP-specific DS/Nitro rendering extension does
# not dirty the libvgm submodule checkout.
set(_tinyksp_libvgm_prepared "${CMAKE_CURRENT_BINARY_DIR}/tinyksp-libvgm")
file(REMOVE_RECURSE "${_tinyksp_libvgm_prepared}")
file(COPY "${_tinyksp_libvgm_checkout}/" DESTINATION "${_tinyksp_libvgm_prepared}")
execute_process(
    COMMAND "${CMAKE_COMMAND}"
        "-DTINYKSP_LIBVGM_SOURCE_DIR=${_tinyksp_libvgm_prepared}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/patch_libvgm.cmake"
    RESULT_VARIABLE _tinyksp_libvgm_patch_result)
if(NOT _tinyksp_libvgm_patch_result EQUAL 0)
    message(FATAL_ERROR "Could not prepare the libvgm checkout for TinyKSP")
endif()
add_subdirectory("${_tinyksp_libvgm_prepared}" "${CMAKE_BINARY_DIR}/libvgm" EXCLUDE_FROM_ALL)

function(tinyksp_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /permissive- /EHsc)
        target_compile_definitions(${target} PRIVATE _CRT_SECURE_NO_WARNINGS NOMINMAX)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endfunction()

add_library(tinyksp_core STATIC
    src/ksp_runtime.cpp
    src/z80.cpp
    src/chips.cpp
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2212/emu2212.c
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2149/emu2149.c
    ${TINYKSP_LIBKSS_SOURCE_DIR}/src/rconv/psg_rconv.c
    src/libvgm_psg.cpp
    src/yamaha_chips.cpp
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2413/emu2413.c
    src/libvgm_ym2413.cpp
    src/libvgm_ymf278b.cpp
    src/ksp_vm.cpp
    src/kss_vm.cpp
)
target_include_directories(tinyksp_core PUBLIC src PRIVATE
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2212
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2149
    ${TINYKSP_LIBKSS_SOURCE_DIR}/src/rconv
    ${TINYKSP_LIBKSS_SOURCE_DIR}/modules/emu2413)
target_link_libraries(tinyksp_core PRIVATE vgm-emu)
tinyksp_warnings(tinyksp_core)

if(APPLE)
    set(TINYKSP_PLATFORM_SOURCES src/native_audio_macos.cpp)
else()
    set(TINYKSP_PLATFORM_SOURCES)
endif()

add_executable(tinyksp src/standalone_player.cpp ${TINYKSP_PLATFORM_SOURCES})
target_link_libraries(tinyksp PRIVATE tinyksp_core)
target_compile_definitions(tinyksp PRIVATE TINYKSP_VERSION="${PROJECT_VERSION}")
tinyksp_warnings(tinyksp)
if(APPLE)
    target_link_libraries(tinyksp PRIVATE "-framework AudioToolbox")
endif()

add_executable(runtime_smoke tests/runtime_smoke.cpp src/ksp_runtime.cpp)
target_include_directories(runtime_smoke PRIVATE src)
tinyksp_warnings(runtime_smoke)

add_executable(z80_smoke tests/z80_smoke.cpp src/z80.cpp)
target_include_directories(z80_smoke PRIVATE src)
tinyksp_warnings(z80_smoke)

add_executable(vm_smoke tests/vm_smoke.cpp)
target_link_libraries(vm_smoke PRIVATE tinyksp_core)
tinyksp_warnings(vm_smoke)

add_executable(ksp103_smoke tests/ksp103_smoke.cpp)
target_link_libraries(ksp103_smoke PRIVATE tinyksp_core)
tinyksp_warnings(ksp103_smoke)

add_executable(ksp104_smoke tests/ksp104_smoke.cpp)
target_link_libraries(ksp104_smoke PRIVATE tinyksp_core)
tinyksp_warnings(ksp104_smoke)

add_executable(ksp105_smoke tests/ksp105_smoke.cpp)
target_link_libraries(ksp105_smoke PRIVATE tinyksp_core)
tinyksp_warnings(ksp105_smoke)

add_executable(yamaha_smoke tests/yamaha_smoke.cpp)
target_link_libraries(yamaha_smoke PRIVATE tinyksp_core)
tinyksp_warnings(yamaha_smoke)

add_executable(yamaha_vm_smoke tests/yamaha_vm_smoke.cpp)
target_link_libraries(yamaha_vm_smoke PRIVATE tinyksp_core)
tinyksp_warnings(yamaha_vm_smoke)

add_executable(kss_vm_smoke tests/kss_vm_smoke.cpp)
target_link_libraries(kss_vm_smoke PRIVATE tinyksp_core)
tinyksp_warnings(kss_vm_smoke)

enable_testing()
add_test(NAME z80_smoke COMMAND z80_smoke)
add_test(NAME yamaha_smoke COMMAND yamaha_smoke)
add_test(NAME kss_vm_smoke COMMAND kss_vm_smoke)

install(TARGETS tinyksp RUNTIME DESTINATION bin)
