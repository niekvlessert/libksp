#include "ksp1_runtime.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void usage(const char *p) {
    fprintf(stderr,"Usage:\n"
      "  %s --info FILE.ksp\n"
      "  %s --validate FILE.ksp\n"
      "  %s --song N --output FILE.kss FILE.ksp\n"
      "  %s --page N --output FILE.bin FILE.ksp\n",p,p,p,p);
}
static int number(const char *s, unsigned max, unsigned *out){char *e;unsigned long v;errno=0;v=strtoul(s,&e,0);if(errno||!*s||*e||v>max)return 0;*out=(unsigned)v;return 1;}
static int write_file(const char *path,const void *data,size_t size){FILE*f=fopen(path,"wb");if(!f)return 0;if(size&&fwrite(data,1,size,f)!=size){fclose(f);return 0;}return fclose(f)==0;}
int main(int argc,char**argv){const char*input=NULL,*output=NULL;int mode=0;unsigned index=0;int i;char error[256];KSP1Runtime*r;const KSP1Header*h;
    for(i=1;i<argc;i++){
        if(!strcmp(argv[i],"--info"))mode=1;
        else if(!strcmp(argv[i],"--validate"))mode=2;
        else if(!strcmp(argv[i],"--song")&&i+1<argc){mode=3;if(!number(argv[++i],65535,&index)){fprintf(stderr,"bad song\n");return 2;}}
        else if(!strcmp(argv[i],"--page")&&i+1<argc){mode=4;if(!number(argv[++i],65535,&index)){fprintf(stderr,"bad page\n");return 2;}}
        else if(!strcmp(argv[i],"--output")&&i+1<argc)output=argv[++i];
        else if(argv[i][0]=='-'){usage(argv[0]);return 2;}else input=argv[i];
    }
    if(!input||!mode||((mode==3||mode==4)&&!output)){usage(argv[0]);return 2;}
    r=ksp1_open(input,error,sizeof(error));if(!r){fprintf(stderr,"error: %s\n",error);return 1;}h=ksp1_header(r);
    if(mode==1){uint16_t n;printf("KSP 1.0: %s\n",input);printf("engines: %u  pages: %u  tracks: %u  resources: %u\n",h->engine_count,h->page_count,h->track_count,h->resource_count);for(n=0;n<h->engine_count;n++){const KSP1Engine*e=ksp1_engine(r,n);const char*name=ksp1_string(r,e->name_offset);printf("engine %u: %s load=$%04X size=%u init=$%04X play=$%04X hw=$%08X pages=%u\n",n,name?name:"(unnamed)",e->load_address,e->page_size,e->init_address,e->play_address,e->hardware_flags,e->page_count);}for(n=0;n<h->track_count;n++){const KSP1Track*t=ksp1_track(r,n);const char*title=ksp1_string(r,t->title_offset);printf("%5u page=%u song=%u %s\n",n,t->page_index,t->song_id,title?title:"");}}
    else if(mode==2){if(!ksp1_validate_all_pages(r,error,sizeof(error))){fprintf(stderr,"error: %s\n",error);ksp1_close(r);return 1;}printf("validated %u pages and %u tracks\n",h->page_count,h->track_count);}
    else if(mode==3){uint8_t*data;uint32_t size;if(index>=h->track_count||!ksp1_build_kscc_image(r,(uint16_t)index,&data,&size,error,sizeof(error))){fprintf(stderr,"error: %s\n",index>=h->track_count?"track out of range":error);ksp1_close(r);return 1;}if(!write_file(output,data,size)){fprintf(stderr,"error: cannot write %s\n",output);free(data);ksp1_close(r);return 1;}free(data);printf("wrote %s\n",output);}
    else {const KSP1Page*p;const KSP1Engine*e;uint8_t*data;if(index>=h->page_count){fprintf(stderr,"error: page out of range\n");ksp1_close(r);return 1;}p=ksp1_page(r,(uint16_t)index);e=ksp1_engine(r,p->engine_index);data=(uint8_t*)malloc(e->page_size);if(!data||!ksp1_materialize_page(r,(uint16_t)index,data,e->page_size,error,sizeof(error))){fprintf(stderr,"error: %s\n",data?error:"out of memory");free(data);ksp1_close(r);return 1;}if(!write_file(output,data,e->page_size)){fprintf(stderr,"error: cannot write %s\n",output);free(data);ksp1_close(r);return 1;}free(data);printf("wrote %s\n",output);}
    ksp1_close(r);return 0;
}
