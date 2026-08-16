#include "ksp_vm.h"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

static bool silent(const std::vector<int16_t>& pcm) {
    auto mm=std::minmax_element(pcm.begin(),pcm.end()); return *mm.first==0&&*mm.second==0;
}
int main(int argc,char**argv){
    if(argc!=3){std::cerr<<"usage: yamaha_vm_smoke FMPAC.ksp OPL4.ksp\n";return 2;}
    for(int n=1;n<=2;++n){
        tinyksp::KspVm vm(44100); std::string e;
        if(!vm.open(argv[n],e)||!vm.start(0,e)){std::cerr<<e<<"\n";return 1;}
        std::vector<int16_t> pcm(44100*2);
        if(!vm.render(pcm.data(),44100,e)||silent(pcm)){std::cerr<<"silent: "<<argv[n]<<" "<<e<<"\n";return 3;}
        if(n==1 && (vm.fmpacWrites()<3||vm.channelCount()!=9)){std::cerr<<"FM-PAC path incomplete\n";return 4;}
        if(n==2 && (vm.opl4FmWrites()<10||vm.opl4PcmWrites()<5||vm.opl4CustomSamples()!=1||vm.channelCount()!=42)){
            std::cerr<<"OPL4 path incomplete "<<vm.opl4FmWrites()<<" "<<vm.opl4PcmWrites()<<" "<<vm.opl4CustomSamples()<<" "<<vm.channelCount()<<"\n";return 5;
        }
        for(int i=0;i<vm.channelCount();++i){bool m=false;if(!vm.toggleChannelMute(i,m)||!m)return 6;}
        std::vector<int16_t> muted(4410*2); if(!vm.render(muted.data(),4410,e)||!silent(muted))return 7;
    }
    std::cout<<"FM-PAC and MoonSound KSP VM integration passed\n";
}
