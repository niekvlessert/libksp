cmake_minimum_required(VERSION 3.16)
project(ksp1_mac_player VERSION 1.0.4 LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(KSP1_BUILD_AUDIO_PLAYER "Build the SDL2/libkss audio player" ON)
option(KSP1_BUILD_TESTS "Build parser/materializer tests" ON)

add_library(ksp1_runtime STATIC
    src/ksp1_runtime.c
    src/ksp1_desktop_bridge.c
    src/ksp1_channel_control.c
    src/ksp1_seek_control.c
    src/zx0.c
)
target_include_directories(ksp1_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
if(MSVC)
    target_compile_options(ksp1_runtime PRIVATE /W4)
else()
    target_compile_options(ksp1_runtime PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(ksp1tool src/ksp1tool.c)
target_link_libraries(ksp1tool PRIVATE ksp1_runtime)

if(KSP1_BUILD_AUDIO_PLAYER)
    set(KSP1_VENDOR_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/vendor/libkss_conversion_tools")
    set(KSP1_LIBKSS_ROOT "${KSP1_VENDOR_ROOT}/3rd_party/libkss")
    if(NOT EXISTS "${KSP1_VENDOR_ROOT}/CMakeLists.txt")
        message(WARNING
            "Bundled libkss is absent. Run scripts/bootstrap-macos.sh. "
            "Only ksp1tool will be built in this configure run.")
    else()
        # Add the upstream repository as an excluded dependency tree. Its CMake
        # applies the repository's current libkss patches (memory-write hook,
        # mapper support, and related fixes). Only target 'kss' is linked here.
        set(_KSP1_SAVED_BUILD_TESTING "${BUILD_TESTING}")
        set(BUILD_TESTING OFF)
        add_subdirectory("${KSP1_VENDOR_ROOT}" vendor-upstream EXCLUDE_FROM_ALL)
        set(BUILD_TESTING "${_KSP1_SAVED_BUILD_TESTING}")
        unset(_KSP1_SAVED_BUILD_TESTING)

        find_package(SDL2 CONFIG QUIET)
        if(TARGET SDL2::SDL2)
            set(KSP1_SDL_TARGET SDL2::SDL2)
        elseif(TARGET SDL2::SDL2-static)
            set(KSP1_SDL_TARGET SDL2::SDL2-static)
        else()
            find_package(PkgConfig REQUIRED)
            pkg_check_modules(SDL2 REQUIRED IMPORTED_TARGET sdl2)
            set(KSP1_SDL_TARGET PkgConfig::SDL2)
        endif()

        add_executable(ksp1player src/ksp1player.c)
        target_compile_definitions(ksp1player PRIVATE SDL_MAIN_HANDLED)
        target_include_directories(ksp1player PRIVATE
            "${KSP1_LIBKSS_ROOT}/src"
            "${KSP1_LIBKSS_ROOT}/modules"
        )
        target_link_libraries(ksp1player PRIVATE
            ksp1_runtime
            kss
            ${KSP1_SDL_TARGET}
        )
        if(TARGET emu2212)
            target_link_libraries(ksp1player PRIVATE emu2212)
        endif()
        if(APPLE)
            target_compile_definitions(ksp1player PRIVATE KSP1_MACOS=1)
        endif()
        if(NOT MSVC)
            target_compile_options(ksp1player PRIVATE -Wall -Wextra -Wpedantic)
        endif()
        install(TARGETS ksp1player ksp1tool RUNTIME DESTINATION bin)
    endif()
endif()

if(KSP1_BUILD_TESTS)
    enable_testing()
    add_executable(ksp1_smoke tests/smoke.c)
    target_link_libraries(ksp1_smoke PRIVATE ksp1_runtime)
    add_test(NAME solid_snake_pages
        COMMAND ksp1_smoke ${CMAKE_CURRENT_SOURCE_DIR}/samples/SOLIDSNK_KSP1_HYBRID_RAM_VRAM.ksp)
    add_test(NAME gazell_pages
        COMMAND ksp1_smoke ${CMAKE_CURRENT_SOURCE_DIR}/samples/XAK_GAZELL_KSP1_HYBRID_RAM_VRAM.ksp)
    add_test(NAME solid_snake_resource_map
        COMMAND ksp1_smoke ${CMAKE_CURRENT_SOURCE_DIR}/samples/SOLIDSNK_KSP1_RESOURCE_MAP.ksp)

    add_executable(ksp1_channel_control tests/channel_control.c)
    target_link_libraries(ksp1_channel_control PRIVATE ksp1_runtime)
    add_test(NAME channel_controls COMMAND ksp1_channel_control)

    add_executable(ksp1_seek_control tests/seek_control.c)
    target_link_libraries(ksp1_seek_control PRIVATE ksp1_runtime)
    add_test(NAME seek_controls COMMAND ksp1_seek_control)

    add_executable(ksp1_dual_scc_bridge tests/dual_scc_bridge.c)
    target_link_libraries(ksp1_dual_scc_bridge PRIVATE ksp1_runtime)
    add_test(NAME eschatos_dual_scc_bridge
        COMMAND ksp1_dual_scc_bridge
            ${CMAKE_CURRENT_SOURCE_DIR}/samples/dual-scc/ESCHATOS_N163_Dual_SCC_KSP1_1.0.ksp
            ksp1)
    add_test(NAME megami_legacy_dual_scc_bridge
        COMMAND ksp1_dual_scc_bridge
            ${CMAKE_CURRENT_SOURCE_DIR}/samples/dual-scc/Megami_Tensei_II_Dual_SCC_KSP1_1.0.ksp
            legacy)
endif()
