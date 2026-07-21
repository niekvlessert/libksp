#include "ksp1_runtime.h"
#include "zx0.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct KSP1Runtime {
    char *path;
    uint8_t *data;
    size_t size;
    KSP1Header header;
    KSP1Engine *engines;
    KSP1Page *pages;
    KSP1Track *tracks;
    KSP1Resource *resources;
    uint8_t **templates;
    struct {
        int loaded;
        uint16_t resource_index;
        uint16_t block_size, position_count, page_count;
        uint16_t hot_count, warm_count, cold_count;
        uint16_t *positions;
        uint8_t *maps;
        uint8_t *blocks;
    } hpol;
};

static void set_error(char *error, size_t error_size, const char *fmt, ...) {
    if (error && error_size) {
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(error, error_size, fmt, ap);
        va_end(ap);
    }
}
static uint16_t rd16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void wr16(uint8_t *p, uint16_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static uint32_t crc32_data(const uint8_t *data, size_t size) {
    uint32_t crc = 0xffffffffu;
    size_t i;
    for (i=0;i<size;i++) {
        unsigned bit;
        crc ^= data[i];
        for (bit=0;bit<8;bit++) crc = (crc >> 1) ^ (0xedb88320u & (0u-(crc&1u)));
    }
    return crc ^ 0xffffffffu;
}
static int range_ok(size_t size, uint64_t offset, uint64_t length) {
    return offset <= size && length <= size - (size_t)offset;
}
static int all_zero(const uint8_t *p, size_t n) { while(n--) if(*p++) return 0; return 1; }
static uint8_t *read_file(const char *path, size_t *size, char *error, size_t error_size) {
    FILE *f; long n; uint8_t *data;
    *size=0; f=fopen(path,"rb"); if(!f){set_error(error,error_size,"cannot open %s",path);return NULL;}
    if(fseek(f,0,SEEK_END)|| (n=ftell(f))<0 || fseek(f,0,SEEK_SET)){fclose(f);set_error(error,error_size,"cannot determine file size");return NULL;}
    data=(uint8_t*)malloc(n?(size_t)n:1); if(!data){fclose(f);set_error(error,error_size,"out of memory");return NULL;}
    if(n && fread(data,1,(size_t)n,f)!=(size_t)n){free(data);fclose(f);set_error(error,error_size,"cannot read file");return NULL;}
    fclose(f); *size=(size_t)n; return data;
}
static int decode_bytes(uint8_t compression, const uint8_t *packed, size_t packed_size,
                        uint8_t *output, size_t output_size, char *error, size_t error_size) {
    if (compression==KSP1_COMPRESSION_NONE) {
        if (packed_size!=output_size) { set_error(error,error_size,"uncompressed size mismatch"); return 0; }
        if (output_size) {
            memcpy(output, packed, output_size);
        }
        return 1;
    }
    if (compression==KSP1_COMPRESSION_ZX0)
        return ksp1_zx0_decompress(packed,packed_size,output,output_size,error,error_size);
    set_error(error,error_size,"unsupported object compression %u",compression); return 0;
}
static int parse_header(KSP1Runtime *r, char *error, size_t error_size) {
    const uint8_t *b=r->data; KSP1Header *h=&r->header; uint8_t tmp[80]; uint32_t crc=0;
    if(r->size<80 || memcmp(b,"KSP1",4) || rd16(b+4)!=80 || rd16(b+6)!=0){set_error(error,error_size,"not KSP 1.0");return 0;}
    if(rd32(b+8)!=0 || rd16(b+0x3e)!=0 || !all_zero(b+0x48,8)){set_error(error,error_size,"unsupported header flags/reserved fields");return 0;}
    h->file_size=rd32(b+0x0c); h->engine_table_offset=rd32(b+0x10); h->engine_count=rd16(b+0x14); h->engine_entry_size=rd16(b+0x16);
    h->page_table_offset=rd32(b+0x18); h->page_count=rd16(b+0x1c); h->page_entry_size=rd16(b+0x1e);
    h->track_table_offset=rd32(b+0x20); h->track_count=rd16(b+0x24); h->track_entry_size=rd16(b+0x26);
    h->resource_table_offset=rd32(b+0x28); h->resource_count=rd16(b+0x2c); h->resource_entry_size=rd16(b+0x2e);
    h->string_table_offset=rd32(b+0x30); h->string_table_size=rd32(b+0x34); h->default_track=rd16(b+0x38); h->meta_resource=rd16(b+0x3a); h->cover_resource=rd16(b+0x3c);
    h->header_crc=rd32(b+0x40); h->index_crc=rd32(b+0x44);
    if(h->file_size!=r->size || h->engine_entry_size<64 || h->page_entry_size<24 || h->track_entry_size<32 || h->resource_entry_size<32){set_error(error,error_size,"invalid file/table dimensions");return 0;}
    if(!range_ok(r->size,h->engine_table_offset,(uint64_t)h->engine_count*h->engine_entry_size)||
       !range_ok(r->size,h->page_table_offset,(uint64_t)h->page_count*h->page_entry_size)||
       !range_ok(r->size,h->track_table_offset,(uint64_t)h->track_count*h->track_entry_size)||
       !range_ok(r->size,h->resource_table_offset,(uint64_t)h->resource_count*h->resource_entry_size)||
       !range_ok(r->size,h->string_table_offset,h->string_table_size)){set_error(error,error_size,"table outside file");return 0;}
    if(h->header_crc){memcpy(tmp,b,80);memset(tmp+0x40,0,4);if(crc32_data(tmp,80)!=h->header_crc){set_error(error,error_size,"header CRC mismatch");return 0;}}
    if(h->index_crc){
        size_t total=(size_t)h->engine_count*h->engine_entry_size+(size_t)h->page_count*h->page_entry_size+(size_t)h->track_count*h->track_entry_size+(size_t)h->resource_count*h->resource_entry_size+h->string_table_size, pos=0;
        uint8_t *idx=(uint8_t*)malloc(total?total:1); if(!idx){set_error(error,error_size,"out of memory");return 0;}
#define APPEND_RANGE(off,len) do{size_t nn=(size_t)(len);memcpy(idx+pos,b+(off),nn);pos+=nn;}while(0)
        APPEND_RANGE(h->engine_table_offset,(size_t)h->engine_count*h->engine_entry_size);
        APPEND_RANGE(h->page_table_offset,(size_t)h->page_count*h->page_entry_size);
        APPEND_RANGE(h->track_table_offset,(size_t)h->track_count*h->track_entry_size);
        APPEND_RANGE(h->resource_table_offset,(size_t)h->resource_count*h->resource_entry_size);
        APPEND_RANGE(h->string_table_offset,h->string_table_size);
#undef APPEND_RANGE
        crc=crc32_data(idx,total); free(idx); if(crc!=h->index_crc){set_error(error,error_size,"index CRC mismatch");return 0;}
    }
    return 1;
}
static int parse_tables(KSP1Runtime *r, char *error, size_t error_size) {
    uint16_t i; const KSP1Header *h=&r->header;
    r->engines=(KSP1Engine*)calloc(h->engine_count,sizeof(*r->engines)); r->pages=(KSP1Page*)calloc(h->page_count,sizeof(*r->pages));
    r->tracks=(KSP1Track*)calloc(h->track_count,sizeof(*r->tracks)); r->resources=(KSP1Resource*)calloc(h->resource_count,sizeof(*r->resources)); r->templates=(uint8_t**)calloc(h->engine_count,sizeof(*r->templates));
    if((h->engine_count&&!r->engines)||(h->page_count&&!r->pages)||(h->track_count&&!r->tracks)||(h->resource_count&&!r->resources)||(h->engine_count&&!r->templates)){set_error(error,error_size,"out of memory");return 0;}
    for(i=0;i<h->engine_count;i++){
        const uint8_t *p=r->data+h->engine_table_offset+(size_t)i*h->engine_entry_size; KSP1Engine *e=&r->engines[i];
        e->flags=rd32(p);e->hardware_flags=rd32(p+4);e->abi_version=rd16(p+8);e->tick_hz=rd16(p+0xa);e->load_address=rd16(p+0xc);e->page_size=rd16(p+0xe);e->init_address=rd16(p+0x10);e->play_address=rd16(p+0x12);e->stop_address=rd16(p+0x14);e->gateway_address=rd16(p+0x16);e->replace_start=rd16(p+0x18);e->first_page=rd16(p+0x1a);e->page_count=rd16(p+0x1c);e->default_mwk=rd16(p+0x1e);e->template_compression=p[0x20];e->bank_base=p[0x21];e->bank_count=p[0x22];e->bank_width=p[0x23];e->template_offset=rd32(p+0x24);e->template_packed_size=rd32(p+0x28);e->template_unpacked_size=rd32(p+0x2c);e->template_crc=rd32(p+0x30);e->name_offset=rd32(p+0x34);
        if(e->abi_version!=1 || !e->page_size || e->template_unpacked_size!=e->page_size || !range_ok(r->size,e->template_offset,e->template_packed_size) || (uint32_t)e->first_page+e->page_count>h->page_count || !all_zero(p+0x38,8)){set_error(error,error_size,"invalid engine %u",i);return 0;}
        if((e->flags&KSP1_ENGINE_DYNAMIC_PAGES) && (!e->gateway_address || e->replace_start<e->load_address || e->replace_start>(uint32_t)e->load_address+e->page_size)){set_error(error,error_size,"invalid dynamic engine %u",i);return 0;}
    }
    for(i=0;i<h->page_count;i++){
        const uint8_t *p=r->data+h->page_table_offset+(size_t)i*h->page_entry_size;KSP1Page *x=&r->pages[i];
        x->engine_index=rd16(p);x->encoding=p[2];x->compression=p[3];x->flags=rd16(p+4);x->payload_offset=rd32(p+8);x->packed_size=rd32(p+0xc);x->unpacked_size=rd32(p+0x10);x->crc=rd32(p+0x14);
        if(x->engine_index>=h->engine_count || rd16(p+6) || x->encoding>4 || !range_ok(r->size,x->payload_offset,x->packed_size)){set_error(error,error_size,"invalid page %u",i);return 0;}
        if(x->encoding==4 && (x->compression||x->flags||x->payload_offset||x->packed_size||x->unpacked_size)){set_error(error,error_size,"invalid hybrid page %u",i);return 0;}
    }
    for(i=0;i<h->engine_count;i++){uint16_t j;KSP1Engine *e=&r->engines[i];for(j=0;j<e->page_count;j++)if(r->pages[e->first_page+j].engine_index!=i){set_error(error,error_size,"engine page ownership mismatch");return 0;}}
    for(i=0;i<h->track_count;i++){
        const uint8_t *p=r->data+h->track_table_offset+(size_t)i*h->track_entry_size;KSP1Track *t=&r->tracks[i];
        t->page_index=rd16(p);t->song_id=rd16(p+2);t->flags=rd16(p+4);t->mwk_resource=rd16(p+6);t->image_resource=rd16(p+8);t->title_offset=rd32(p+0xc);t->duration_ms=rd32(p+0x10);t->loop_start_ms=rd32(p+0x14);t->loop_end_ms=rd32(p+0x18);t->fade_ms=rd32(p+0x1c);
        if(t->page_index>=h->page_count || rd16(p+0xa) || (t->mwk_resource!=KSP1_NO_INDEX&&t->mwk_resource>=h->resource_count)||(t->image_resource!=KSP1_NO_INDEX&&t->image_resource>=h->resource_count)){set_error(error,error_size,"invalid track %u",i);return 0;}
    }
    for(i=0;i<h->resource_count;i++){
        const uint8_t *p=r->data+h->resource_table_offset+(size_t)i*h->resource_entry_size;KSP1Resource *x=&r->resources[i];
        memcpy(x->type,p,4);x->type[4]=0;x->flags=rd16(p+4);x->compression=p[6];x->offset=rd32(p+8);x->packed_size=rd32(p+0xc);x->unpacked_size=rd32(p+0x10);x->crc=rd32(p+0x14);x->aux0=rd32(p+0x18);x->aux1=rd32(p+0x1c);
        if(p[7] || !range_ok(r->size,x->offset,x->packed_size) || x->compression>2){set_error(error,error_size,"invalid resource %u",i);return 0;}
    }
    return 1;
}
static int load_template(KSP1Runtime *r,uint16_t index,char *error,size_t error_size){KSP1Engine *e;uint8_t *out;if(index>=r->header.engine_count)return 0;if(r->templates[index])return 1;e=&r->engines[index];out=(uint8_t*)malloc(e->page_size);if(!out){set_error(error,error_size,"out of memory");return 0;}if(!decode_bytes(e->template_compression,r->data+e->template_offset,e->template_packed_size,out,e->page_size,error,error_size)){free(out);return 0;}if(e->template_crc&&crc32_data(out,e->page_size)!=e->template_crc){free(out);set_error(error,error_size,"template CRC mismatch");return 0;}r->templates[index]=out;return 1;}
static int decode_kzb1(const uint8_t *p,size_t n,uint8_t *out,size_t out_size,char *error,size_t error_size){uint16_t count,i;uint32_t total,to;size_t dest=0;if(n<16||memcmp(p,"KZB1",4)||rd16(p+4)!=16){set_error(error,error_size,"invalid KZB1");return 0;}count=rd16(p+6);total=rd32(p+8);to=rd32(p+0xc);if(total!=out_size||!range_ok(n,to,(uint64_t)count*16)){set_error(error,error_size,"invalid KZB1 dimensions");return 0;}for(i=0;i<count;i++){const uint8_t*d=p+to+(size_t)i*16;uint32_t po=rd32(d),ps=rd32(d+4),us=rd32(d+8),cc=rd32(d+12);if(!range_ok(n,po,ps)||us>out_size-dest||!ksp1_zx0_decompress(p+po,ps,out+dest,us,error,error_size)){return 0;}if(cc&&crc32_data(out+dest,us)!=cc){set_error(error,error_size,"KZB1 block CRC mismatch");return 0;}dest+=us;}if(dest!=out_size){set_error(error,error_size,"KZB1 output mismatch");return 0;}return 1;}
static int decode_resource(KSP1Runtime*r,uint16_t index,char*error,size_t error_size){KSP1Resource*x;uint8_t*out;if(index>=r->header.resource_count){set_error(error,error_size,"resource out of range");return 0;}x=&r->resources[index];if(x->decoded)return 1;if(!strcmp(x->type,"PBLK")||!strcmp(x->type,"HPOL")){set_error(error,error_size,"container resource is not a byte source");return 0;}out=(uint8_t*)malloc(x->unpacked_size?x->unpacked_size:1);if(!out){set_error(error,error_size,"out of memory");return 0;}if(x->compression==2){if(!decode_kzb1(r->data+x->offset,x->packed_size,out,x->unpacked_size,error,error_size)){free(out);return 0;}}else if(!decode_bytes(x->compression,r->data+x->offset,x->packed_size,out,x->unpacked_size,error,error_size)){free(out);return 0;}if(x->crc&&crc32_data(out,x->unpacked_size)!=x->crc){free(out);set_error(error,error_size,"resource %.4s CRC mismatch",x->type);return 0;}x->decoded=out;return 1;}
static int decode_pool_block(KSP1Runtime*r,uint16_t ri,uint32_t bi,uint8_t*out,size_t out_capacity,size_t*block_size,char*error,size_t error_size){KSP1Resource*x;const uint8_t*p,*bd,*sd;uint16_t hs,bds,sds,bs,sc,si,src,us;uint32_t bc,bto,sto,po,ps,cc;uint8_t comp,*slab;if(ri>=r->header.resource_count||(x=&r->resources[ri],strcmp(x->type,"PBLK"))){set_error(error,error_size,"invalid PBLK reference");return 0;}p=r->data+x->offset;if(x->packed_size<32||memcmp(p,"PBK1",4)){set_error(error,error_size,"invalid PBK1");return 0;}hs=rd16(p+4);bds=rd16(p+6);sds=rd16(p+8);bs=rd16(p+0xa);bc=rd32(p+0xc);sc=rd16(p+0x10);bto=rd32(p+0x14);sto=rd32(p+0x18);if(hs!=32||bds<8||sds<16||bi>=bc||bs>out_capacity||!range_ok(x->packed_size,bto,(uint64_t)bc*bds)||!range_ok(x->packed_size,sto,(uint64_t)sc*sds)){set_error(error,error_size,"invalid PBK1 dimensions");return 0;}bd=p+bto+(size_t)bi*bds;si=rd16(bd);src=rd16(bd+2);if(si>=sc){set_error(error,error_size,"invalid PBK1 slab index");return 0;}sd=p+sto+(size_t)si*sds;po=rd32(sd);ps=rd32(sd+4);us=rd16(sd+8);comp=sd[0xa];cc=rd32(sd+0xc);if(sd[0xb]||!us||us>16384||src+bs>us||!range_ok(x->packed_size,po,ps)){set_error(error,error_size,"invalid PBK1 slab");return 0;}slab=(uint8_t*)malloc(us);if(!slab){set_error(error,error_size,"out of memory");return 0;}if(!decode_bytes(comp,p+po,ps,slab,us,error,error_size)){free(slab);return 0;}if(cc&&crc32_data(slab,us)!=cc){free(slab);set_error(error,error_size,"PBK1 slab CRC mismatch");return 0;}memcpy(out,slab+src,bs);free(slab);*block_size=bs;return 1;}
static int load_hpol(KSP1Runtime*r,char*error,size_t error_size){uint16_t ri,i,hs,ver,bs,pc,posc,hc,wc,cc,sc,flags;KSP1Resource*x=NULL;const uint8_t*p;uint32_t posoff,mapoff,mappk,mapraw,hotoff,hotpk,hotraw,warmoff,warmpk,warmraw,ctoff,cdoff,cpt,crs,hcrc,wcrc,ccrc,mcrc;uint8_t*cold;size_t coldpos=0,totalblocks;
    if (r->hpol.loaded) {
        return 1;
    }
    ri = KSP1_NO_INDEX;
    for (i = 0; i < r->header.resource_count; i++) {
        if (!strcmp(r->resources[i].type, "HPOL")) {
            if (ri != KSP1_NO_INDEX) {
                set_error(error, error_size, "multiple HPOL resources");
                return 0;
            }
            ri = i;
        }
    }
    if (ri == KSP1_NO_INDEX) {
        set_error(error, error_size, "missing HPOL resource");
        return 0;
    }
    x = &r->resources[ri];
    if (x->compression != 0) {
        set_error(error, error_size, "HPOL resource compression must be NONE");
        return 0;
    }
    p = r->data + x->offset;
    if (x->packed_size < 96 || memcmp(p, "HPL1", 4)) {
        set_error(error, error_size, "invalid HPL1");
        return 0;
    }
    hs=rd16(p+4);ver=rd16(p+6);bs=rd16(p+8);posc=rd16(p+0xa);pc=rd16(p+0xc);hc=rd16(p+0xe);wc=rd16(p+0x10);cc=rd16(p+0x12);sc=rd16(p+0x14);flags=rd16(p+0x16);posoff=rd32(p+0x18);mapoff=rd32(p+0x1c);mappk=rd32(p+0x20);mapraw=rd32(p+0x24);hotoff=rd32(p+0x28);hotpk=rd32(p+0x2c);hotraw=rd32(p+0x30);warmoff=rd32(p+0x34);warmpk=rd32(p+0x38);warmraw=rd32(p+0x3c);ctoff=rd32(p+0x40);cdoff=rd32(p+0x44);cpt=rd32(p+0x48);crs=rd32(p+0x4c);hcrc=rd32(p+0x50);wcrc=rd32(p+0x54);ccrc=rd32(p+0x58);mcrc=rd32(p+0x5c);
    (void)cdoff;(void)cpt;if(hs!=96||ver!=1||(flags&~1u)||!bs||pc!=r->header.page_count||hotraw!=(uint32_t)hc*bs||warmraw!=(uint32_t)wc*bs||crs!=(uint32_t)cc*bs||mapraw!=(uint32_t)pc*posc*2||!range_ok(x->packed_size,posoff,(uint64_t)posc*2)||!range_ok(x->packed_size,mapoff,mappk)||!range_ok(x->packed_size,hotoff,hotpk)||!range_ok(x->packed_size,warmoff,warmpk)||!range_ok(x->packed_size,ctoff,(uint64_t)sc*16)){set_error(error,error_size,"invalid HPL1 dimensions");return 0;}
    r->hpol.positions=(uint16_t*)malloc((size_t)posc*sizeof(uint16_t));r->hpol.maps=(uint8_t*)malloc(mapraw?mapraw:1);totalblocks=(size_t)hc+wc+cc;r->hpol.blocks=(uint8_t*)malloc((totalblocks != 0 && bs != 0) ? (totalblocks * bs) : 1);if(!r->hpol.positions||!r->hpol.maps||!r->hpol.blocks){set_error(error,error_size,"out of memory");return 0;}
    for(i=0;i<posc;i++)r->hpol.positions[i]=rd16(p+posoff+(size_t)i*2);
    if(mapraw&&!ksp1_zx0_decompress(p+mapoff,mappk,r->hpol.maps,mapraw,error,error_size))return 0;
    if(hotraw&&!ksp1_zx0_decompress(p+hotoff,hotpk,r->hpol.blocks,hotraw,error,error_size))return 0;
    if(warmraw&&!ksp1_zx0_decompress(p+warmoff,warmpk,r->hpol.blocks+hotraw,warmraw,error,error_size))return 0;
    cold=r->hpol.blocks+hotraw+warmraw;
    for(i=0;i<sc;i++){const uint8_t*d=p+ctoff+(size_t)i*16;uint32_t po=rd32(d),ps=rd32(d+4),crc=rd32(d+0xc);uint16_t us=rd16(d+8);uint8_t comp=d[0xa];if(d[0xb]||!us||us>16384||us%bs||coldpos+us>crs||!range_ok(x->packed_size,po,ps)||!decode_bytes(comp,p+po,ps,cold+coldpos,us,error,error_size))return 0;if(crc&&crc32_data(cold+coldpos,us)!=crc){set_error(error,error_size,"HPL1 cold slab CRC mismatch");return 0;}coldpos+=us;}
    if(coldpos!=crs||(hcrc&&crc32_data(r->hpol.blocks,hotraw)!=hcrc)||(wcrc&&crc32_data(r->hpol.blocks+hotraw,warmraw)!=wcrc)||(ccrc&&crc32_data(cold,crs)!=ccrc)||(mcrc&&crc32_data(r->hpol.maps,mapraw)!=mcrc)){set_error(error,error_size,"HPL1 CRC mismatch");return 0;}
    r->hpol.loaded=1;r->hpol.resource_index=ri;r->hpol.block_size=bs;r->hpol.position_count=posc;r->hpol.page_count=pc;r->hpol.hot_count=hc;r->hpol.warm_count=wc;r->hpol.cold_count=cc;return 1;
}
KSP1Runtime *ksp1_open(const char *path,char*error,size_t error_size){KSP1Runtime*r=(KSP1Runtime*)calloc(1,sizeof(*r));if(error&&error_size)error[0]=0;if(!r){set_error(error,error_size,"out of memory");return NULL;}r->data=read_file(path,&r->size,error,error_size);if(!r->data||!parse_header(r,error,error_size)||!parse_tables(r,error,error_size)){ksp1_close(r);return NULL;}r->path=(char*)malloc(strlen(path)+1);if(r->path)strcpy(r->path,path);return r;}
void ksp1_close(KSP1Runtime*r){uint16_t i;if(!r)return;if(r->resources)for(i=0;i<r->header.resource_count;i++)free(r->resources[i].decoded);if(r->templates)for(i=0;i<r->header.engine_count;i++)free(r->templates[i]);free(r->hpol.positions);free(r->hpol.maps);free(r->hpol.blocks);free(r->templates);free(r->resources);free(r->tracks);free(r->pages);free(r->engines);free(r->data);free(r->path);free(r);}
const KSP1Header*ksp1_header(const KSP1Runtime*r){return r?&r->header:NULL;}const KSP1Engine*ksp1_engine(const KSP1Runtime*r,uint16_t i){return r&&i<r->header.engine_count?&r->engines[i]:NULL;}const KSP1Page*ksp1_page(const KSP1Runtime*r,uint16_t i){return r&&i<r->header.page_count?&r->pages[i]:NULL;}const KSP1Track*ksp1_track(const KSP1Runtime*r,uint16_t i){return r&&i<r->header.track_count?&r->tracks[i]:NULL;}const KSP1Resource*ksp1_resource(const KSP1Runtime*r,uint16_t i){return r&&i<r->header.resource_count?&r->resources[i]:NULL;}
const char*ksp1_string(const KSP1Runtime*r,uint32_t off){const uint8_t*s,*end;if(!r||off==KSP1_NO_STRING||off>=r->header.string_table_size)return NULL;s=r->data+r->header.string_table_offset+off;end=r->data+r->header.string_table_offset+r->header.string_table_size;return memchr(s,0,(size_t)(end-s))?(const char*)s:NULL;}
int ksp1_materialize_page(KSP1Runtime*r,uint16_t pi,uint8_t*out,size_t out_size,char*error,size_t error_size){KSP1Page*x;KSP1Engine*e;uint8_t*payload=NULL;uint32_t cursor=0;if(!r||pi>=r->header.page_count){set_error(error,error_size,"page out of range");return 0;}x=&r->pages[pi];e=&r->engines[x->engine_index];if(out_size<e->page_size){set_error(error,error_size,"output buffer too small");return 0;}if(!load_template(r,x->engine_index,error,error_size))return 0;if((x->flags&1u)&&(x->encoding==2||x->encoding==3))memset(out,0,e->page_size);else memcpy(out,r->templates[x->engine_index],e->page_size);
    if(x->encoding==1){if(!decode_bytes(x->compression,r->data+x->payload_offset,x->packed_size,out,e->page_size,error,error_size))return 0;}
    else if(x->encoding==0||x->encoding==2||x->encoding==3){payload=(uint8_t*)malloc(x->unpacked_size?x->unpacked_size:1);if(!payload){set_error(error,error_size,"out of memory");return 0;}if(!decode_bytes(x->compression,r->data+x->payload_offset,x->packed_size,payload,x->unpacked_size,error,error_size)){free(payload);return 0;}
        if(x->encoding==0){while(cursor<x->unpacked_size){uint16_t d,n;if(x->unpacked_size-cursor<4){free(payload);set_error(error,error_size,"truncated sparse overlay");return 0;}d=rd16(payload+cursor);n=rd16(payload+cursor+2);cursor+=4;if(!n||n>x->unpacked_size-cursor||d>e->page_size||n>e->page_size-d){free(payload);set_error(error,error_size,"invalid sparse overlay");return 0;}memcpy(out+d,payload+cursor,n);cursor+=n;}}
        else if(x->encoding==2){uint16_t hs,ri,n,rs,j;uint8_t*block=(uint8_t*)malloc(e->page_size);size_t bs;if(x->unpacked_size<16||memcmp(payload,"PBM1",4)){free(block);free(payload);set_error(error,error_size,"invalid PBM1");return 0;}hs=rd16(payload+4);ri=rd16(payload+6);n=rd16(payload+8);rs=rd16(payload+0xa);if(hs!=16||rs<12||!range_ok(x->unpacked_size,hs,(uint64_t)n*rs)){free(block);free(payload);set_error(error,error_size,"invalid PBM1 dimensions");return 0;}for(j=0;j<n;j++){const uint8_t*d=payload+hs+(size_t)j*rs;uint16_t dest=rd16(d),len=rd16(d+2),src=rd16(d+8);uint32_t bi=rd32(d+4);if(rd16(d+0xa)||!decode_pool_block(r,ri,bi,block,e->page_size,&bs,error,error_size)||!len||dest+len>e->page_size||src+len>bs){free(block);free(payload);return 0;}memcpy(out+dest,block+src,len);}free(block);}
        else {uint16_t hs,n,rs,j;if(x->unpacked_size<16||memcmp(payload,"RMP1",4)){free(payload);set_error(error,error_size,"invalid RMP1");return 0;}hs=rd16(payload+4);n=rd16(payload+6);rs=rd16(payload+8);if(hs!=16||rs<16||rd16(payload+0xa)||rd32(payload+0xc)||!range_ok(x->unpacked_size,hs,(uint64_t)n*rs)){free(payload);set_error(error,error_size,"invalid RMP1 dimensions");return 0;}for(j=0;j<n;j++){const uint8_t*d=payload+hs+(size_t)j*rs;uint16_t dest=rd16(d),len=rd16(d+2),ri=rd16(d+6);uint8_t typ=d[4];uint32_t src=rd32(d+8);if(!len||d[5]||rd32(d+0xc)||dest+len>e->page_size){free(payload);set_error(error,error_size,"invalid RMP1 record");return 0;}if(typ==0){if(ri>=r->header.resource_count||!(r->resources[ri].flags&KSP1_RESOURCE_PAGE_SOURCE)||src+len>r->resources[ri].unpacked_size||!decode_resource(r,ri,error,error_size)){free(payload);return 0;}memcpy(out+dest,r->resources[ri].decoded+src,len);}else if(typ==1){if(ri!=KSP1_NO_INDEX||src+len>x->unpacked_size){free(payload);set_error(error,error_size,"invalid inline RMP1 record");return 0;}memcpy(out+dest,payload+src,len);}else if(typ==2){if(ri!=KSP1_NO_INDEX||(src&0xffffff00u)){free(payload);set_error(error,error_size,"invalid fill RMP1 record");return 0;}memset(out+dest,(int)(src&255u),len);}else{free(payload);set_error(error,error_size,"unknown RMP1 record");return 0;}}}
        free(payload);
    } else if(x->encoding==4){uint16_t j;if(!load_hpol(r,error,error_size))return 0;if(pi>=r->hpol.page_count){set_error(error,error_size,"hybrid page row out of range");return 0;}for(j=0;j<r->hpol.position_count;j++){uint16_t dest=r->hpol.positions[j],bi=rd16(r->hpol.maps+((size_t)pi*r->hpol.position_count+j)*2);size_t total=(size_t)r->hpol.hot_count+r->hpol.warm_count+r->hpol.cold_count;if(bi>=total||dest+r->hpol.block_size>e->page_size){set_error(error,error_size,"invalid hybrid block map");return 0;}memcpy(out+dest,r->hpol.blocks+(size_t)bi*r->hpol.block_size,r->hpol.block_size);}}
    else {set_error(error,error_size,"unknown page encoding");return 0;}
    if(x->crc&&crc32_data(out,e->page_size)!=x->crc){set_error(error,error_size,"page %u CRC mismatch",pi);return 0;}return 1;
}
int ksp1_materialize_track(KSP1Runtime*r,uint16_t ti,uint8_t**output,size_t*out_size,const KSP1Engine**engine,const KSP1Track**track,char*error,size_t error_size){KSP1Track*t;KSP1Page*p;KSP1Engine*e;uint8_t*b;if(!r||ti>=r->header.track_count){set_error(error,error_size,"track out of range");return 0;}t=&r->tracks[ti];p=&r->pages[t->page_index];e=&r->engines[p->engine_index];b=(uint8_t*)malloc(e->page_size);if(!b){set_error(error,error_size,"out of memory");return 0;}if(!ksp1_materialize_page(r,t->page_index,b,e->page_size,error,error_size)){free(b);return 0;}*output=b;*out_size=e->page_size;if(engine)*engine=e;if(track)*track=t;return 1;}
int ksp1_validate_all_pages(KSP1Runtime*r,char*error,size_t error_size){uint16_t i;for(i=0;i<r->header.page_count;i++){KSP1Engine*e=&r->engines[r->pages[i].engine_index];uint8_t*b=(uint8_t*)malloc(e->page_size);if(!b){set_error(error,error_size,"out of memory");return 0;}if(!ksp1_materialize_page(r,i,b,e->page_size,error,error_size)){free(b);return 0;}free(b);}return 1;}
static uint8_t kss_device_flags(uint32_t hw, uint16_t tick_hz) {
    uint8_t flags = 0;
    /* Legacy KSCC device byte as parsed by libkss:
     * bit 0 = YM2413/FMPAC (or Sega FM when SN76489 is selected)
     * bit 1 = SN76489/Sega mode
     * bit 2 = Game Gear stereo in Sega mode
     * bit 3 = Y8950/MSX-AUDIO in MSX mode
     * bit 6 = PAL/50 Hz
     * PSG and SCC are baseline MSX devices and need no flag.
     */
    if (hw & (1u << 4)) flags |= 0x01u;
    if (hw & (1u << 5)) flags |= 0x08u;
    if (hw & (1u << 7)) flags |= 0x02u;
    if (hw & (1u << 8)) flags |= 0x04u;
    if (tick_hz == 50u) flags |= 0x40u;
    return flags;
}
int ksp1_build_kscc_image(KSP1Runtime*r,uint16_t ti,uint8_t**image,uint32_t*image_size,char*error,size_t error_size){uint8_t*page,*out;size_t page_size;const KSP1Engine*e;const KSP1Track*t;if(!ksp1_materialize_track(r,ti,&page,&page_size,&e,&t,error,error_size))return 0;if(page_size>65535u){free(page);set_error(error,error_size,"page too large for KSCC bridge");return 0;}out=(uint8_t*)malloc(16+page_size);if(!out){free(page);set_error(error,error_size,"out of memory");return 0;}memset(out,0,16);memcpy(out,"KSCC",4);wr16(out+4,e->load_address);wr16(out+6,(uint16_t)page_size);wr16(out+8,e->init_address);wr16(out+10,e->play_address);out[15]=kss_device_flags(e->hardware_flags,e->tick_hz);memcpy(out+16,page,page_size);free(page);*image=out;*image_size=(uint32_t)(16+page_size);(void)t;return 1;}
